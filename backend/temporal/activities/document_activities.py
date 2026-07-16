"""
Activities for DocumentWorkflow.

Each function is a discrete, independently-retryable unit:
  update_file_status    — Postgres write (cheap, retry freely)
  read_and_split_file   — disk read + text splitting; writes chunks to a temp JSON
                          file instead of returning them — avoids Temporal's 4 MB
                          payload limit on large documents
  clear_existing_vectors — ChromaDB delete (cheap, retry freely)
  embed_and_index_chunks — reads chunks from the temp file, embeds via OpenAI,
                           indexes to ChromaDB, then deletes the temp file

Raising ApplicationError(non_retryable=True) signals Temporal to stop retrying.
"""

import json
import time
import uuid
from pathlib import Path

from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

import db.models  # noqa: F401 — side-effect import: registers all SQLAlchemy mappers
from config import settings
from db.models.file import File
from db.session import AsyncSessionFactory
from observability import metrics as m
from services.llm import get_embedding_provider
from services.llm.base import ProviderAuthError
from services.project_chunk_service import _read_file, _split_text
from vectorstore.chroma_store import add_chunks
from vectorstore.chroma_store import delete_file as chroma_delete_file


def _chunks_path(project_id: str, file_id: str) -> Path:
    """Temp file that holds the split chunks between activities."""
    return settings.upload_dir / project_id / f"{file_id}_chunks.json"


@activity.defn
async def update_file_status(
    file_id: str, status: str, chunk_count: int | None = None
) -> None:
    async with AsyncSessionFactory() as db:
        result = await db.execute(select(File).where(File.id == uuid.UUID(file_id)))
        record = result.scalar_one()
        record.chunk_status = status
        if chunk_count is not None:
            record.chunk_count = chunk_count
        await db.commit()


@activity.defn
async def read_and_split_file(file_id: str, project_id: str) -> dict:
    """
    Reads the document, splits into chunks, and writes them to a temp JSON file.
    Returns {"filename": str, "chunk_count": int} — small payload, no size limit issues.
    Non-retryable if the source file is missing from disk.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(select(File).where(File.id == uuid.UUID(file_id)))
        record = result.scalar_one()
        filepath = record.filepath
        filename = record.filename

    path = Path(filepath)
    if not path.exists():
        raise ApplicationError(
            f"File not found on disk: {path}",
            non_retryable=True,
        )

    text = _read_file(path)
    chunks = _split_text(text)

    # Write chunks to disk — keeps Temporal history payload tiny
    out = _chunks_path(project_id, file_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"filename": filename, "chunks": chunks}))

    return {"filename": filename, "chunk_count": len(chunks)}


@activity.defn
async def clear_existing_vectors(project_id: str, file_id: str) -> None:
    chroma_delete_file(project_id, file_id)


@activity.defn
async def embed_and_index_chunks(project_id: str, file_id: str) -> int:
    """
    Reads chunks from the temp file, embeds via OpenAI, indexes to ChromaDB,
    then cleans up the temp file.
    Wrong API key → non-retryable. Rate limit / network → retried by Temporal.
    """
    out = _chunks_path(project_id, file_id)
    if not out.exists():
        raise ApplicationError(
            f"Chunks file missing: {out}",
            non_retryable=True,
        )

    data = json.loads(out.read_text())
    filename: str = data["filename"]
    chunks: list[str] = data["chunks"]

    attrs = {
        "rag.activity_name": "embed_and_index_chunks",
        "rag.project_id": project_id,
        "rag.collection_name": project_id,
        "rag.model": settings.embedding_model,
        "rag.embedding_model": settings.embedding_model,
        "rag.provider": settings.embedding_provider,
        "rag.call_site": "chunk_batch",
    }
    info = activity.info()
    attrs["rag.workflow_id"] = info.workflow_id
    attrs["rag.workflow_type"] = info.workflow_type

    m.embedding_batch_size.record(len(chunks), attrs)

    # ── Embed ──────────────────────────────────────────────────────────────────
    t_embed = time.perf_counter()
    try:
        embeddings, usage_tokens = await _embed_with_usage(chunks)
    except ProviderAuthError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "AUTH_ERROR", "non_retryable": "true"}
        )
        raise ApplicationError(str(exc), non_retryable=True) from exc

    embed_latency_ms = (time.perf_counter() - t_embed) * 1000
    m.embedding_latency.record(embed_latency_ms, attrs)
    m.embedding_requests_total.add(1, attrs)
    m.requests_embedding_total.add(1, attrs)
    if usage_tokens:
        m.embedding_tokens_total.add(usage_tokens, attrs)
        m.tokens_embedding_total.add(usage_tokens, attrs)

    if activity.info().attempt > 1:
        m.workflow_retries_total.add(1, {**attrs, "error_type": "UNKNOWN"})

    # ── Index to ChromaDB ─────────────────────────────────────────────────────
    chunk_dicts = [
        {
            "id": str(uuid.uuid4()),
            "file_id": file_id,
            "filename": filename,
            "chunk_index": i,
            "content": text,
        }
        for i, text in enumerate(chunks)
    ]

    chroma_attrs = {
        "rag.activity_name": "embed_and_index_chunks",
        "rag.collection_name": project_id,
        "rag.provider": "chroma",
        "rag.project_id": project_id,
    }

    t_insert = time.perf_counter()
    add_chunks(project_id, chunk_dicts, embeddings)
    insert_latency_ms = (time.perf_counter() - t_insert) * 1000

    m.vectordb_insert_latency.record(insert_latency_ms, chroma_attrs)
    m.vectordb_insert_count_total.add(1, chroma_attrs)

    # ── Collection size (cheap metadata call, not a full scan) ────────────────
    try:
        from vectorstore.chroma_store import collection_count

        count = collection_count(project_id)
        m.update_vectordb_size(project_id, project_id, count)
    except Exception:
        pass  # collection size is best-effort; never fail the activity over it

    out.unlink(missing_ok=True)
    return len(chunks)


_EMBED_BATCH = 100  # matches project_chunk_service.EMBED_BATCH


async def _embed_with_usage(chunks: list[str]) -> tuple[list[list[float]], int]:
    """
    Embeds chunks in batches (same batch size as project_chunk_service)
    and accumulates total token usage across all batches.
    Returns (embeddings, total_tokens).
    """
    provider = get_embedding_provider()
    vectors: list[list[float]] = []
    total_tokens = 0

    for i in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[i : i + _EMBED_BATCH]
        result = await provider.embed(model=settings.embedding_model, texts=batch)
        vectors.extend(result.embeddings)
        total_tokens += result.total_tokens

    return vectors, total_tokens
