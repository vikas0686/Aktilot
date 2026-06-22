import uuid

from pydantic import BaseModel, ConfigDict
from datetime import datetime


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
    score: float  # final hybrid score
    vec_score: float = 0.0  # cosine similarity component
    bm25_score: float = 0.0  # BM25 component
    kw_hits: int = 0  # number of keywords found in chunk
    keywords_matched: list[str] = []


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    tool_steps: list[ToolStep]
    retrieved_chunks: list[RetrievedChunk]
    keywords: list[str] = []  # keywords extracted from the question


# ── Projects ──────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


# ── Project Files ─────────────────────────────────────────────────────────────


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    size: int
    chunk_status: str
    chunk_count: int
    uploaded_at: datetime


# ── Messages ─────────────────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    role: str
    content: str
    created_at: datetime


# ── Agents ────────────────────────────────────────────────────────────────────


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str = ""
    top_k: int = 2


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    top_k: int | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    system_prompt: str
    top_k: int
    created_at: datetime
