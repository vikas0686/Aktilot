"""Background sweep that removes orphaned upload files/directories.

Uploaded files are normally cleaned up when their File row or Project row is
deleted (see project_file_service.delete / project_service.delete). But files
can end up orphaned on disk without ever going through those code paths —
most commonly when the database is reset/restored without touching the
uploads directory (routine in local development), or if the process crashes
between writing the file and committing its File row. Left unchecked these
accumulate on disk forever, since nothing else on the read/write path ever
revisits them.

A grace period (settings.upload_orphan_grace_minutes) protects any file or
project directory modified too recently from being swept, so an in-flight
upload can never be deleted out from under a request whose transaction
hasn't committed yet.
"""

import logging
import shutil
import time
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models.file import File
from db.models.project import Project

logger = logging.getLogger(__name__)


def _older_than_grace_period(path: Path, grace_minutes: int) -> bool:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False
    return (time.time() - mtime) > grace_minutes * 60


async def sweep_orphaned_uploads(db: AsyncSession) -> int:
    """Deletes on-disk upload files/directories with no corresponding DB
    record and returns the number of items removed."""
    if not settings.upload_dir.exists():
        return 0

    grace_minutes = settings.upload_orphan_grace_minutes
    removed = 0

    project_ids = {
        str(pid) for pid in (await db.execute(select(Project.id))).scalars().all()
    }

    for project_dir in settings.upload_dir.iterdir():
        if not project_dir.is_dir():
            continue

        if project_dir.name not in project_ids:
            if _older_than_grace_period(project_dir, grace_minutes):
                shutil.rmtree(project_dir, ignore_errors=True)
                removed += 1
                logger.info(
                    "upload sweep: removed orphaned project dir %s", project_dir.name
                )
            continue

        try:
            project_id = uuid.UUID(project_dir.name)
        except ValueError:
            continue

        file_ids = {
            str(fid)
            for fid in (
                await db.execute(select(File.id).where(File.project_id == project_id))
            )
            .scalars()
            .all()
        }

        for f in project_dir.iterdir():
            if not f.is_file():
                continue
            file_id = f.name.split("_", 1)[0]
            if file_id not in file_ids and _older_than_grace_period(f, grace_minutes):
                f.unlink(missing_ok=True)
                removed += 1
                logger.info("upload sweep: removed orphaned file %s", f)

    return removed
