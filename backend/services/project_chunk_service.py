from pathlib import Path

from pypdf import PdfReader

from config import settings
from services.llm import get_embedding_provider

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
    provider = get_embedding_provider()
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        result = await provider.embed(model=settings.embedding_model, texts=batch)
        embeddings.extend(result.embeddings)
    return embeddings
