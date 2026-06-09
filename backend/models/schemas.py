from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class FileRecord(BaseModel):
    id: str
    filename: str
    size: int
    uploaded_at: datetime
    chunk_status: str = "not_chunked"  # not_chunked | chunking | chunked
    chunk_count: int = 0


class ChunkRecord(BaseModel):
    id: str
    file_id: str
    filename: str
    chunk_index: int
    content: str


class ToolStep(BaseModel):
    name: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    input_summary: str
    output_summary: str


class RetrievedChunk(BaseModel):
    chunk_id: str
    filename: str
    chunk_index: int
    content: str
    score: float


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    tool_steps: list[ToolStep]
    retrieved_chunks: list[RetrievedChunk]


class ChunkStats(BaseModel):
    total_chunks: int
    total_files_chunked: int
    index_size: int
