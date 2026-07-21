import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.github_connection import GithubConnection
from vectorstore.chroma_store import delete_by_repo as chroma_delete_by_repo


async def create(
    db: AsyncSession,
    project_id: uuid.UUID,
    installation_id: uuid.UUID,
    repo_full_name: str,
    default_branch: str,
) -> GithubConnection:
    existing = await db.execute(
        select(GithubConnection).where(
            GithubConnection.project_id == project_id,
            GithubConnection.repo_full_name == repo_full_name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail=f"{repo_full_name} is already connected"
        )

    record = GithubConnection(
        project_id=project_id,
        installation_id=installation_id,
        repo_full_name=repo_full_name,
        default_branch=default_branch,
        sync_status="pending",
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail=f"{repo_full_name} is already connected"
        )
    await db.refresh(record)
    return record


async def list_for_project(
    db: AsyncSession, project_id: uuid.UUID
) -> list[GithubConnection]:
    result = await db.execute(
        select(GithubConnection)
        .where(GithubConnection.project_id == project_id)
        .order_by(GithubConnection.created_at.desc())
    )
    return list(result.scalars().all())


async def get(
    db: AsyncSession,
    connection_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> GithubConnection:
    stmt = select(GithubConnection).where(GithubConnection.id == connection_id)
    if project_id is not None:
        stmt = stmt.where(GithubConnection.project_id == project_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="GitHub connection not found")
    return record


async def mark_syncing(db: AsyncSession, connection_id: uuid.UUID) -> None:
    record = await get(db, connection_id)
    record.sync_status = "syncing"
    record.error_message = None
    await db.commit()


async def mark_synced(
    db: AsyncSession,
    connection_id: uuid.UUID,
    file_count: int,
    issue_count: int,
    chunk_count: int,
) -> None:
    record = await get(db, connection_id)
    record.sync_status = "synced"
    record.file_count = file_count
    record.issue_count = issue_count
    record.chunk_count = chunk_count
    record.last_synced_at = datetime.now(timezone.utc)
    record.error_message = None
    await db.commit()


async def mark_error(db: AsyncSession, connection_id: uuid.UUID, message: str) -> None:
    record = await get(db, connection_id)
    record.sync_status = "error"
    record.error_message = message
    await db.commit()


async def delete(
    db: AsyncSession,
    connection_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    record = await get(db, connection_id, project_id)
    chroma_delete_by_repo(str(project_id), str(connection_id))
    await db.delete(record)
    await db.commit()
