"""
Unit tests for vectorstore/chroma_store.py.

Like the rest of the suite, chromadb itself is mocked at the module level in
conftest.py (sys.modules["chromadb"] = MagicMock()) so these tests assert
against the mocked collection's call log rather than exercising real Chroma
storage. What matters for retry-safety is (a) add_chunks calls upsert, not
add, and (b) two calls with the same chunk IDs produce the same ID list —
Chroma's upsert is documented to replace-by-id, so identical IDs across calls
is what makes embed_and_index_chunks idempotent under a Temporal retry.
"""

from unittest.mock import MagicMock

import pytest

from vectorstore import chroma_store


@pytest.fixture
def mock_collection(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(chroma_store, "get_collection", lambda project_id: collection)
    return collection


def _chunk(chunk_id: str, content: str, chunk_index: int) -> dict:
    return {
        "id": chunk_id,
        "content": content,
        "metadata": {
            "file_id": "f1",
            "filename": "doc.txt",
            "chunk_index": chunk_index,
        },
    }


def test_add_chunks_calls_upsert_not_add(mock_collection):
    chunks = [_chunk("f1:0", "a", 0), _chunk("f1:1", "b", 1)]

    chroma_store.add_chunks("proj1", chunks, [[0.1], [0.2]])

    mock_collection.upsert.assert_called_once_with(
        ids=["f1:0", "f1:1"],
        embeddings=[[0.1], [0.2]],
        documents=["a", "b"],
        metadatas=[chunks[0]["metadata"], chunks[1]["metadata"]],
    )
    mock_collection.add.assert_not_called()


def test_add_chunks_retry_with_same_ids_upserts_the_same_records(mock_collection):
    """Simulates a Temporal activity retry: the same deterministic chunk IDs
    are submitted twice with (possibly) freshly re-embedded vectors. Both
    calls must target the same IDs — combined with Chroma upsert's
    replace-by-id semantics, this is what prevents duplicate chunks."""
    chunks = [_chunk("f1:0", "a", 0), _chunk("f1:1", "b", 1), _chunk("f1:2", "c", 2)]

    chroma_store.add_chunks("proj1", chunks, [[0.1], [0.2], [0.3]])
    chroma_store.add_chunks("proj1", chunks, [[0.9], [0.8], [0.7]])

    assert mock_collection.upsert.call_count == 2
    first_ids = mock_collection.upsert.call_args_list[0].kwargs["ids"]
    second_ids = mock_collection.upsert.call_args_list[1].kwargs["ids"]
    assert first_ids == second_ids == ["f1:0", "f1:1", "f1:2"]
