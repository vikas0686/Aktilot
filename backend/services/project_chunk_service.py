import uuid
from pathlib import Path

from openai import AsyncOpenAI, AuthenticationError, RateLimitError
from pypdf import PdfReader

from config import settings
from db.session import AsyncSessionFactory
from services.project_file_service import get as get_file
from vectorstore.chroma_store import add_chunks, delete_file as chroma_delete_file

client = AsyncOpenAI(api_key=settings.openai_api_key)

CHUNK_SIZE = 1000
OVERLAP = 200
EMBED_BATCH = 100


def _read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if path.suffix.lower() in (".doc", ".docx"):
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")


def _split_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - OVERLAP
    return chunks


async def _embed(texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = await client.embeddings.create(model=settings.embedding_model, input=batch)
        embeddings.extend([d.embedding for d in resp.data])
    return embeddings


async def chunk_file(file_id: str, project_id: str) -> None:
    """Background task: read → split → embed → store in ChromaDB → update DB status.

    Opens its own DB session because the request session is closed before this runs.
    """
    fid = uuid.UUID(file_id)

    async with AsyncSessionFactory() as db:
        record = await get_file(db, fid)
        record.chunk_status = "chunking"
        await db.commit()

        try:
            path = Path(record.filepath)
            if not path.exists():
                raise FileNotFoundError(f"File not on disk: {path}")

            text = _read_file(path)
            raw_chunks = _split_text(text)

            chunks = [
                {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "filename": record.filename,
                    "chunk_index": i,
                    "content": chunk,
                }
                for i, chunk in enumerate(raw_chunks)
            ]

            # Clear any previous vectors for this file before re-inserting
            chroma_delete_file(project_id, file_id)

            embeddings = await _embed([c["content"] for c in chunks])
            add_chunks(project_id, chunks, embeddings)

            record.chunk_status = "chunked"
            record.chunk_count = len(chunks)
            await db.commit()

        except (AuthenticationError, RateLimitError):
            record.chunk_status = "error"
            await db.commit()
            raise
        except Exception:
            record.chunk_status = "error"
            await db.commit()
            raise
