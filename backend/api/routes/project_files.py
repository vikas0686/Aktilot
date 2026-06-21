import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from config import project_upload_dir
from db.session import get_db
from models.schemas import FileResponse
from services import project_file_service, project_chunk_service, project_service

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".doc", ".docx"}

router = APIRouter(prefix="/api/projects", tags=["project-files"])


@router.post(
    "/{project_id}/files/upload",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    await project_service.get(db, project_id)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    file_id = uuid.uuid4()
    upload_dir = project_upload_dir(str(project_id))
    dest = upload_dir / f"{file_id}_{file.filename}"

    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    record = await project_file_service.create(
        db,
        project_id=project_id,
        filename=file.filename,
        filepath=str(dest.resolve()),
        size=len(content),
        file_id=file_id,
    )

    background_tasks.add_task(
        project_chunk_service.chunk_file,
        str(record.id),
        str(project_id),
    )

    return record


@router.get("/{project_id}/files", response_model=list[FileResponse])
async def list_files(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await project_service.get(db, project_id)
    return await project_file_service.list_for_project(db, project_id)


@router.delete(
    "/{project_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_file(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await project_file_service.delete(db, file_id, project_id)
