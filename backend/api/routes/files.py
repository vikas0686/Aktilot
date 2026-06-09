from fastapi import APIRouter, UploadFile, File
from services import file_service
from models.schemas import FileRecord

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload", response_model=FileRecord)
async def upload_file(file: UploadFile = File(...)):
    return await file_service.save_file(file)


@router.get("", response_model=list[FileRecord])
def list_files():
    return file_service.list_files()


@router.delete("/{file_id}", status_code=204)
def delete_file(file_id: str):
    file_service.delete_file(file_id)
