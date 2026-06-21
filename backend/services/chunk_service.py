import uuid
from pathlib import Path

from fastapi import HTTPException
from openai import AsyncOpenAI
from pypdf import PdfReader

from config import settings
from models.schemas import ChunkRecord
from vectorstore.faiss_store import vector_store
from services import file_service

client = AsyncOpenAI(api_key=settings.openai_api_key)

CHUNK_SIZE = 1000
OVERLAP = 200
EMBED_BATCH = 100


def _split_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - OVERLAP
    return chunks


def _read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if path.suffix.lower() in (".doc", ".docx"):
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")


async def _embed(texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = await client.embeddings.create(
            model=settings.embedding_model, input=batch
        )
        embeddings.extend([d.embedding for d in resp.data])
    return embeddings


async def chunk_file(file_id: str) -> int:
    record = file_service.get_file(file_id)
    path = settings.context_dir / record.filename
    if not path.exists():
        raise HTTPException(404, "File not found on disk")

    file_service.update_chunk_status(file_id, "chunking")

    try:
        text = _read_file(path)
        raw_chunks = _split_text(text)

        chunk_records = [
            ChunkRecord(
                id=str(uuid.uuid4()),
                file_id=file_id,
                filename=record.filename,
                chunk_index=i,
                content=chunk,
            )
            for i, chunk in enumerate(raw_chunks)
        ]

        # Remove old chunks for this file before adding new ones
        vector_store.remove_file(file_id)

        embeddings = await _embed([c.content for c in chunk_records])
        vector_store.add(chunk_records, embeddings)

        file_service.update_chunk_status(file_id, "chunked", len(chunk_records))
        return len(chunk_records)
    except HTTPException:
        file_service.update_chunk_status(file_id, "not_chunked")
        raise
    except Exception as e:
        file_service.update_chunk_status(file_id, "not_chunked")
        from openai import AuthenticationError, RateLimitError

        if isinstance(e, AuthenticationError):
            raise HTTPException(
                401, "Invalid OpenAI API key. Check OPENAI_API_KEY in your .env file."
            )
        if isinstance(e, RateLimitError):
            raise HTTPException(429, "OpenAI rate limit exceeded. Try again shortly.")
        raise HTTPException(500, f"Chunking failed: {e}")
