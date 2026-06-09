"""In-memory FAISS vector store singleton."""
import numpy as np
from typing import Optional
import faiss

from models.schemas import ChunkRecord


class FAISSStore:
    def __init__(self):
        self.dimension = 1536  # text-embedding-3-small
        self.index: Optional[faiss.IndexFlatIP] = None
        self.chunks: list[ChunkRecord] = []
        self.embeddings: list[list[float]] = []

    def _rebuild_index(self):
        if not self.embeddings:
            self.index = None
            return
        matrix = np.array(self.embeddings, dtype=np.float32)
        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(matrix)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(matrix)

    def add(self, chunks: list[ChunkRecord], embeddings: list[list[float]]):
        self.chunks.extend(chunks)
        self.embeddings.extend(embeddings)
        self._rebuild_index()

    def remove_file(self, file_id: str):
        pairs = [(c, e) for c, e in zip(self.chunks, self.embeddings) if c.file_id != file_id]
        if pairs:
            self.chunks, self.embeddings = zip(*pairs)
            self.chunks = list(self.chunks)
            self.embeddings = list(self.embeddings)
        else:
            self.chunks, self.embeddings = [], []
        self._rebuild_index()

    def search(self, query_embedding: list[float], k: int = 10) -> list[tuple[ChunkRecord, float]]:
        if self.index is None or len(self.chunks) == 0:
            return []
        vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        k = min(k, len(self.chunks))
        scores, indices = self.index.search(vec, k)
        return [(self.chunks[i], float(scores[0][j])) for j, i in enumerate(indices[0]) if i >= 0]

    @property
    def size(self) -> int:
        return len(self.chunks)


vector_store = FAISSStore()
