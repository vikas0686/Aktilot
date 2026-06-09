from fastapi import APIRouter
from services import chunk_service
from vectorstore.faiss_store import vector_store
from services.file_service import list_files
from models.schemas import ChunkStats

router = APIRouter(prefix="/api", tags=["chunks"])


@router.post("/chunk/{file_id}")
async def chunk_file(file_id: str):
    count = await chunk_service.chunk_file(file_id)
    return {"chunksCreated": count}


@router.get("/chunks/stats", response_model=ChunkStats)
def get_stats():
    files_chunked = sum(1 for f in list_files() if f.chunk_status == "chunked")
    return ChunkStats(
        total_chunks=vector_store.size,
        total_files_chunked=files_chunked,
        index_size=vector_store.size,
    )
