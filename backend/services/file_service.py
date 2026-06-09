import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import UploadFile, HTTPException

from config import settings
from models.schemas import FileRecord
from vectorstore.faiss_store import vector_store

# In-memory store: file_id -> FileRecord
_files: dict[str, FileRecord] = {}


async def save_file(upload: UploadFile) -> FileRecord:
    if not upload.filename:
        raise HTTPException(400, "Missing filename")
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in (".pdf", ".txt", ".doc", ".docx"):
        raise HTTPException(400, "Only PDF, TXT, DOC and DOCX files are supported")

    file_id = str(uuid.uuid4())
    dest = settings.context_dir / upload.filename

    content = await upload.read()
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    record = FileRecord(
        id=file_id,
        filename=upload.filename,
        size=len(content),
        uploaded_at=datetime.now(timezone.utc),
    )
    _files[file_id] = record
    return record


def list_files() -> list[FileRecord]:
    return list(_files.values())


def get_file(file_id: str) -> FileRecord:
    record = _files.get(file_id)
    if not record:
        raise HTTPException(404, "File not found")
    return record


def delete_file(file_id: str) -> None:
    record = get_file(file_id)
    path = settings.context_dir / record.filename
    if path.exists():
        path.unlink()
    vector_store.remove_file(file_id)
    del _files[file_id]


def update_chunk_status(file_id: str, status: str, count: int = 0):
    record = get_file(file_id)
    record.chunk_status = status
    record.chunk_count = count
