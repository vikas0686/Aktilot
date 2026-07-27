"""
Unit tests for services/upload_sweeper.py.

Uses the shared db_session fixture (in-memory SQLite) plus a tmp_path stood
in for settings.upload_dir. Files/directories are backdated with os.utime so
grace-period behavior can be tested deterministically instead of sleeping.
"""

import os
import time
import uuid

import pytest

from config import settings
from db.models.file import File
from db.models.project import Project
from services import upload_sweeper

GRACE_MINUTES = 60


def _backdate(path, minutes_ago: float) -> None:
    ts = time.time() - minutes_ago * 60
    os.utime(path, (ts, ts))


@pytest.fixture(autouse=True)
def _upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    # Paths in these tests are backdated relative to GRACE_MINUTES, so the
    # sweeper must use that same value — not whatever grace period a
    # non-default environment happens to have configured.
    monkeypatch.setattr(settings, "upload_orphan_grace_minutes", GRACE_MINUTES)
    return tmp_path


async def _make_project(db_session) -> Project:
    project = Project(name="p")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _make_file(db_session, project: Project) -> File:
    record = File(
        id=uuid.uuid4(),
        project_id=project.id,
        filename="doc.txt",
        filepath="unused",
        size=1,
        chunk_status="pending",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


async def test_old_orphaned_project_dir_is_removed(db_session, _upload_dir):
    orphan_dir = _upload_dir / str(uuid.uuid4())
    orphan_dir.mkdir()
    _backdate(orphan_dir, minutes_ago=GRACE_MINUTES + 1)

    removed = await upload_sweeper.sweep_orphaned_uploads(db_session)

    assert removed == 1
    assert not orphan_dir.exists()


async def test_recent_orphaned_project_dir_is_kept(db_session, _upload_dir):
    """A dir with no DB-matching project but modified within the grace period
    must survive — it might belong to an upload whose transaction hasn't
    committed yet."""
    orphan_dir = _upload_dir / str(uuid.uuid4())
    orphan_dir.mkdir()

    removed = await upload_sweeper.sweep_orphaned_uploads(db_session)

    assert removed == 0
    assert orphan_dir.exists()


async def test_old_orphaned_file_in_real_project_is_removed(db_session, _upload_dir):
    project = await _make_project(db_session)
    project_dir = _upload_dir / str(project.id)
    project_dir.mkdir()
    orphan_file = project_dir / f"{uuid.uuid4()}_ghost.txt"
    orphan_file.write_text("x")
    _backdate(orphan_file, minutes_ago=GRACE_MINUTES + 1)

    removed = await upload_sweeper.sweep_orphaned_uploads(db_session)

    assert removed == 1
    assert not orphan_file.exists()
    # the project directory itself (a known project) is untouched
    assert project_dir.exists()


async def test_file_with_matching_db_record_is_kept(db_session, _upload_dir):
    project = await _make_project(db_session)
    file_record = await _make_file(db_session, project)
    project_dir = _upload_dir / str(project.id)
    project_dir.mkdir()
    real_file = project_dir / f"{file_record.id}_doc.txt"
    real_file.write_text("x")
    _backdate(real_file, minutes_ago=GRACE_MINUTES + 1)

    removed = await upload_sweeper.sweep_orphaned_uploads(db_session)

    assert removed == 0
    assert real_file.exists()


async def test_recent_orphaned_file_in_real_project_is_kept(db_session, _upload_dir):
    project = await _make_project(db_session)
    project_dir = _upload_dir / str(project.id)
    project_dir.mkdir()
    fresh_orphan = project_dir / f"{uuid.uuid4()}_just_uploaded.txt"
    fresh_orphan.write_text("x")

    removed = await upload_sweeper.sweep_orphaned_uploads(db_session)

    assert removed == 0
    assert fresh_orphan.exists()


async def test_missing_upload_dir_returns_zero(db_session, tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(settings, "upload_dir", missing)

    removed = await upload_sweeper.sweep_orphaned_uploads(db_session)

    assert removed == 0
