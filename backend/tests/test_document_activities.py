"""
Unit tests for temporal/activities/document_activities.py.

Mirrors tests/test_chat_activities.py's approach: activities are called
directly as plain async functions, except embed_and_index_chunks which reads
activity.info() for observability attributes and needs ActivityEnvironment.
Each test patches only the external dependency under test — AsyncSessionFactory,
get_embedding_provider, add_chunks/chroma_delete_file, or settings.upload_dir
(to redirect the on-disk chunks temp file into pytest's tmp_path).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import NoResultFound
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from services.llm.base import EmbedResult, ProviderAuthError, ProviderNotAvailableError
from temporal.activities.document_activities import (
    _chunks_path,
    clear_existing_vectors,
    embed_and_index_chunks,
    read_and_split_file,
    update_file_status,
)

_env = ActivityEnvironment()

# update_file_status / read_and_split_file parse file_id as a real UUID;
# the other activities (clear_existing_vectors, embed_and_index_chunks) treat
# it as an opaque string, so plain "f1"-style ids are fine for those.
FILE_ID = "11111111-1111-1111-1111-111111111111"


def _mock_db_factory(file=None):
    """Patch for AsyncSessionFactory whose `execute(...).scalar_one()` returns
    `file`, or raises NoResultFound if file is None — matching the real
    SQLAlchemy behavior these activities rely on (they use scalar_one(), not
    scalar_one_or_none(), so a missing row is an exception, not None)."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    if file is None:
        mock_result.scalar_one.side_effect = NoResultFound()
    else:
        mock_result.scalar_one.return_value = file
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _embed_factory(vectors, tokens=10):
    provider = MagicMock()
    provider.embed = AsyncMock(
        return_value=EmbedResult(embeddings=vectors, total_tokens=tokens)
    )
    return MagicMock(return_value=provider)


# ── update_file_status ────────────────────────────────────────────────────────


async def test_update_file_status_sets_status_and_commits():
    mock_file = MagicMock(chunk_status="pending", chunk_count=0)
    factory = _mock_db_factory(file=mock_file)
    with patch("temporal.activities.document_activities.AsyncSessionFactory", factory):
        await update_file_status(FILE_ID, "chunking")

    assert mock_file.chunk_status == "chunking"
    assert mock_file.chunk_count == 0  # untouched — chunk_count wasn't passed


async def test_update_file_status_sets_chunk_count_when_provided():
    mock_file = MagicMock(chunk_status="chunking", chunk_count=0)
    factory = _mock_db_factory(file=mock_file)
    with patch("temporal.activities.document_activities.AsyncSessionFactory", factory):
        await update_file_status(FILE_ID, "chunked", chunk_count=42)

    assert mock_file.chunk_status == "chunked"
    assert mock_file.chunk_count == 42


async def test_update_file_status_missing_file_raises():
    """Unlike get_agent_config, this activity has no not-found handling —
    a missing row surfaces as a raw NoResultFound, not an ApplicationError.
    Documents current (asymmetric-with-chat) behavior."""
    factory = _mock_db_factory(file=None)
    with patch("temporal.activities.document_activities.AsyncSessionFactory", factory):
        with pytest.raises(NoResultFound):
            await update_file_status("00000000-0000-0000-0000-000000000000", "chunking")


# ── read_and_split_file ───────────────────────────────────────────────────────


async def test_read_and_split_file_happy_path(tmp_path, monkeypatch):
    src = tmp_path / "source.txt"
    src.write_text("hello world " * 200)  # long enough to split into >1 chunk

    mock_file = MagicMock(filepath=str(src), filename="source.txt")
    factory = _mock_db_factory(file=mock_file)
    monkeypatch.setattr(
        "temporal.activities.document_activities.settings.upload_dir", tmp_path
    )

    with patch("temporal.activities.document_activities.AsyncSessionFactory", factory):
        result = await read_and_split_file(FILE_ID, "proj1")

    assert result["filename"] == "source.txt"
    assert result["chunk_count"] > 1

    out = _chunks_path("proj1", FILE_ID)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["filename"] == "source.txt"
    assert len(data["chunks"]) == result["chunk_count"]


async def test_read_and_split_file_missing_on_disk_raises_non_retryable(
    tmp_path, monkeypatch
):
    mock_file = MagicMock(
        filepath=str(tmp_path / "does-not-exist.txt"), filename="x.txt"
    )
    factory = _mock_db_factory(file=mock_file)
    monkeypatch.setattr(
        "temporal.activities.document_activities.settings.upload_dir", tmp_path
    )

    with patch("temporal.activities.document_activities.AsyncSessionFactory", factory):
        with pytest.raises(ApplicationError) as exc:
            await read_and_split_file(FILE_ID, "proj1")

    assert exc.value.non_retryable is True


async def test_read_and_split_file_missing_db_row_raises():
    factory = _mock_db_factory(file=None)
    with patch("temporal.activities.document_activities.AsyncSessionFactory", factory):
        with pytest.raises(NoResultFound):
            await read_and_split_file("00000000-0000-0000-0000-000000000000", "proj1")


# ── clear_existing_vectors ────────────────────────────────────────────────────


async def test_clear_existing_vectors_delegates_to_chroma_delete_file():
    with patch(
        "temporal.activities.document_activities.chroma_delete_file"
    ) as mock_delete:
        await clear_existing_vectors("proj1", "f1")

    mock_delete.assert_called_once_with("proj1", "f1")


# ── embed_and_index_chunks ────────────────────────────────────────────────────


def _write_chunks_file(
    tmp_path: Path,
    monkeypatch,
    project_id: str,
    file_id: str,
    chunks: list[str],
    filename="doc.txt",
):
    monkeypatch.setattr(
        "temporal.activities.document_activities.settings.upload_dir", tmp_path
    )
    out = _chunks_path(project_id, file_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"filename": filename, "chunks": chunks}))
    return out


async def test_embed_and_index_chunks_happy_path(tmp_path, monkeypatch):
    out = _write_chunks_file(tmp_path, monkeypatch, "proj1", "f1", ["a", "b", "c"])
    factory = _embed_factory([[0.1], [0.2], [0.3]])

    with (
        patch(
            "temporal.activities.document_activities.get_embedding_provider", factory
        ),
        patch("temporal.activities.document_activities.add_chunks") as mock_add,
    ):
        count = await _env.run(embed_and_index_chunks, "proj1", "f1")

    assert count == 3
    mock_add.assert_called_once()
    call_args = mock_add.call_args
    assert call_args.args[0] == "proj1"
    chunk_dicts = call_args.args[1]
    assert [c["content"] for c in chunk_dicts] == ["a", "b", "c"]
    assert [c["metadata"]["chunk_index"] for c in chunk_dicts] == [0, 1, 2]
    assert all(
        c["metadata"]["file_id"] == "f1" and c["metadata"]["filename"] == "doc.txt"
        for c in chunk_dicts
    )
    assert call_args.args[2] == [[0.1], [0.2], [0.3]]

    # temp chunks file is cleaned up after a successful run
    assert not out.exists()


async def test_embed_and_index_chunks_missing_file_raises_non_retryable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "temporal.activities.document_activities.settings.upload_dir", tmp_path
    )
    with pytest.raises(ApplicationError) as exc:
        await _env.run(embed_and_index_chunks, "proj1", "does-not-exist")

    assert exc.value.non_retryable is True


async def test_embed_and_index_chunks_auth_error_raises_non_retryable_and_keeps_temp_file(
    tmp_path, monkeypatch
):
    out = _write_chunks_file(tmp_path, monkeypatch, "proj1", "f1", ["a"])
    provider = MagicMock()
    provider.embed = AsyncMock(side_effect=ProviderAuthError("bad key"))

    with patch(
        "temporal.activities.document_activities.get_embedding_provider",
        MagicMock(return_value=provider),
    ):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(embed_and_index_chunks, "proj1", "f1")

    assert exc.value.non_retryable is True
    # Failure happens before cleanup — the chunks file must still be there so
    # a retried workflow attempt (if the error type were ever retryable) could
    # still read it.
    assert out.exists()


async def test_embed_and_index_chunks_config_error_raises_non_retryable(
    tmp_path, monkeypatch
):
    _write_chunks_file(tmp_path, monkeypatch, "proj1", "f1", ["a"])
    provider = MagicMock()
    provider.embed = AsyncMock(
        side_effect=ProviderNotAvailableError("unknown provider")
    )

    with patch(
        "temporal.activities.document_activities.get_embedding_provider",
        MagicMock(return_value=provider),
    ):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(embed_and_index_chunks, "proj1", "f1")

    assert exc.value.non_retryable is True


async def test_embed_and_index_chunks_batches_over_embed_batch_size(
    tmp_path, monkeypatch
):
    """EMBED_BATCH is 100 — 250 chunks must be embedded in 3 batches
    (100 + 100 + 50), each producing its own embed() call."""
    chunks = [f"chunk-{i}" for i in range(250)]
    _write_chunks_file(tmp_path, monkeypatch, "proj1", "f1", chunks)

    provider = MagicMock()

    async def _embed(model, texts):
        return EmbedResult(embeddings=[[0.0]] * len(texts), total_tokens=len(texts))

    provider.embed = AsyncMock(side_effect=_embed)

    with (
        patch(
            "temporal.activities.document_activities.get_embedding_provider",
            MagicMock(return_value=provider),
        ),
        patch("temporal.activities.document_activities.add_chunks") as mock_add,
    ):
        count = await _env.run(embed_and_index_chunks, "proj1", "f1")

    assert count == 250
    assert provider.embed.call_count == 3
    batch_sizes = [len(call.kwargs["texts"]) for call in provider.embed.call_args_list]
    assert batch_sizes == [100, 100, 50]
    assert len(mock_add.call_args.args[1]) == 250
    assert len(mock_add.call_args.args[2]) == 250


async def test_embed_and_index_chunks_collection_count_failure_is_non_fatal(
    tmp_path, monkeypatch
):
    """collection_count is best-effort observability — a failure there must
    never fail the activity."""
    _write_chunks_file(tmp_path, monkeypatch, "proj1", "f1", ["a"])
    factory = _embed_factory([[0.1]])

    with (
        patch(
            "temporal.activities.document_activities.get_embedding_provider", factory
        ),
        patch("temporal.activities.document_activities.add_chunks"),
        patch(
            "vectorstore.chroma_store.collection_count",
            side_effect=RuntimeError("chromadb unavailable"),
        ),
    ):
        count = await _env.run(embed_and_index_chunks, "proj1", "f1")

    assert count == 1
