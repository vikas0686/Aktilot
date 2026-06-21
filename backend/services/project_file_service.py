import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.file import File
from vectorstore.chroma_store import delete_file as chroma_delete_file


async def create(
    db: AsyncSession,
    project_id: uuid.UUID,
    filename: str,
    filepath: str,
    size: int,
    file_id: uuid.UUID | None = None,
) -> File:
    record = File(
        id=file_id or uuid.uuid4(),
        project_id=project_id,
        filename=filename,
        filepath=filepath,
        size=size,
        chunk_status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def list_for_project(db: AsyncSession, project_id: uuid.UUID) -> list[File]:
    result = await db.execute(
        select(File)
        .where(File.project_id == project_id)
        .order_by(File.uploaded_at.desc())
    )
    return list(result.scalars().all())


async def get(
    db: AsyncSession,
    file_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> File:
    stmt = select(File).where(File.id == file_id)
    if project_id is not None:
        stmt = stmt.where(File.project_id == project_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")
    return record


async def delete(
    db: AsyncSession,
    file_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    record = await get(db, file_id, project_id)

    # Remove chunks from ChromaDB
    chroma_delete_file(str(project_id), str(file_id))

    # Remove from disk
    path = Path(record.filepath)
    if path.exists():
        path.unlink()

    await db.delete(record)
    await db.commit()
