import shutil
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models.project import Project
from vectorstore.chroma_store import delete_project as chroma_delete_project


async def create(db: AsyncSession, name: str, description: str | None) -> Project:
    project = Project(name=name, description=description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_all(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


async def get(db: AsyncSession, project_id: uuid.UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def delete(db: AsyncSession, project_id: uuid.UUID) -> None:
    project = await get(db, project_id)

    # Remove uploaded files from disk
    upload_path = settings.upload_dir / str(project_id)
    if upload_path.exists():
        shutil.rmtree(upload_path)

    # Remove ChromaDB collection
    chroma_delete_project(str(project_id))

    # Remove from DB — cascades to files, agents, messages
    await db.delete(project)
    await db.commit()
