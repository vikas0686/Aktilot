"""Persistent ChromaDB vector store, scoped per project."""

import chromadb

from config import settings

_client = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return _client


def get_collection(project_id: str) -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=f"project_{project_id}",
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    project_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    """
    chunks: list of {id, file_id, filename, chunk_index, content}
    """
    collection = get_collection(project_id)
    collection.add(
        ids=[c["id"] for c in chunks],
        embeddings=embeddings,
        documents=[c["content"] for c in chunks],
        metadatas=[
            {
                "file_id": c["file_id"],
                "filename": c["filename"],
                "chunk_index": c["chunk_index"],
            }
            for c in chunks
        ],
    )


def search(
    project_id: str,
    query_embedding: list[float],
    k: int = 20,
) -> list[dict]:
    """Returns [{id, content, metadata, distance}, ...]  sorted by ascending distance."""
    collection = get_collection(project_id)
    total = collection.count()
    if total == 0:
        return []
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, total),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {
            "id": doc_id,
            "content": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        }
        for i, doc_id in enumerate(results["ids"][0])
    ]


def delete_file(project_id: str, file_id: str) -> None:
    """Remove all chunks belonging to file_id from the project collection."""
    collection = get_collection(project_id)
    existing = collection.get(where={"file_id": file_id})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])


def delete_project(project_id: str) -> None:
    """Drop the entire collection for a project."""
    try:
        _get_client().delete_collection(name=f"project_{project_id}")
    except Exception:
        pass


def collection_count(project_id: str) -> int:
    return get_collection(project_id).count()
