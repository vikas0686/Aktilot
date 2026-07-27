"""
Unit tests for temporal/activities/github_activities.py.

Mirrors tests/test_document_activities.py's approach: activities are called
directly as plain async functions, except the three that call
activity.heartbeat() (fetch_file_contents, fetch_issues,
embed_and_index_github_chunks), which need ActivityEnvironment. Each test
patches only the external dependency under test — AsyncSessionFactory,
services.github.client / get_installation_token, get_embedding_provider,
add_chunks/chroma_delete_by_repo, or settings.upload_dir (to redirect the
on-disk temp files into pytest's tmp_path).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import NoResultFound
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from services.github import client as gh_client
from services.llm.base import EmbedResult, ProviderAuthError, ProviderNotAvailableError
from temporal.activities.github_activities import (
    _file_chunks_path,
    _issue_chunks_path,
    _should_index_path,
    _tree_path,
    clear_existing_vectors_for_repo,
    embed_and_index_github_chunks,
    fetch_file_contents,
    fetch_issues,
    fetch_repo_tree,
    mark_connection_error,
    mark_connection_synced,
    mark_connection_syncing,
)

_env = ActivityEnvironment()

# mark_connection_* parse connection_id as a real UUID; the other activities
# treat it as an opaque string, so this one id works everywhere.
CONNECTION_ID = "11111111-1111-1111-1111-111111111111"


def _mock_db_factory(connection=None):
    """Patch for AsyncSessionFactory whose `execute(...).scalar_one()` returns
    `connection`, or raises NoResultFound if connection is None."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    if connection is None:
        mock_result.scalar_one.side_effect = NoResultFound()
    else:
        mock_result.scalar_one.return_value = connection
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


def _write_file_chunks(tmp_path, monkeypatch, project_id, connection_id, chunks):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    out = _file_chunks_path(project_id, connection_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(chunks))
    return out


def _write_issue_chunks(tmp_path, monkeypatch, project_id, connection_id, chunks):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    out = _issue_chunks_path(project_id, connection_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(chunks))
    return out


# ── _should_index_path ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,size,expected",
    [
        ("src/main.py", 100, True),
        ("README.md", 10, True),
        ("src/main.py", 600_000, False),  # over _MAX_BLOB_SIZE
        (".git/config", 10, False),
        ("node_modules/foo/index.js", 10, False),
        ("frontend/node_modules/foo/index.js", 10, False),  # nested prefix match
        ("package-lock.json", 10, False),
        ("backend/package-lock.json", 10, False),  # filename check, not prefix
        ("assets/logo.png", 10, False),
        ("assets/logo.PNG", 10, False),  # extension match is case-insensitive
    ],
)
def test_should_index_path(path, size, expected):
    assert _should_index_path(path, size) is expected


# ── mark_connection_syncing / synced / error ─────────────────────────────────


async def test_mark_connection_syncing_sets_status_and_clears_error():
    mock_conn = MagicMock(sync_status="pending", error_message="old error")
    factory = _mock_db_factory(mock_conn)
    with patch("temporal.activities.github_activities.AsyncSessionFactory", factory):
        await mark_connection_syncing(CONNECTION_ID)

    assert mock_conn.sync_status == "syncing"
    assert mock_conn.error_message is None


async def test_mark_connection_syncing_missing_row_raises():
    factory = _mock_db_factory(connection=None)
    with patch("temporal.activities.github_activities.AsyncSessionFactory", factory):
        with pytest.raises(NoResultFound):
            await mark_connection_syncing("00000000-0000-0000-0000-000000000000")


async def test_mark_connection_synced_sets_all_fields():
    mock_conn = MagicMock(sync_status="syncing", error_message="x")
    factory = _mock_db_factory(mock_conn)
    with patch("temporal.activities.github_activities.AsyncSessionFactory", factory):
        await mark_connection_synced(
            CONNECTION_ID,
            file_count=3,
            issue_count=2,
            chunk_count=10,
            tree_truncated=True,
        )

    assert mock_conn.sync_status == "synced"
    assert mock_conn.file_count == 3
    assert mock_conn.issue_count == 2
    assert mock_conn.chunk_count == 10
    assert mock_conn.tree_truncated is True
    assert mock_conn.error_message is None
    assert mock_conn.last_synced_at is not None


async def test_mark_connection_error_sets_status_and_truncates_message():
    mock_conn = MagicMock(sync_status="syncing")
    factory = _mock_db_factory(mock_conn)
    long_message = "x" * 3000
    with patch("temporal.activities.github_activities.AsyncSessionFactory", factory):
        await mark_connection_error(CONNECTION_ID, long_message)

    assert mock_conn.sync_status == "error"
    assert mock_conn.error_message == long_message[:2000]
    assert len(mock_conn.error_message) == 2000


# ── fetch_repo_tree ───────────────────────────────────────────────────────────


async def test_fetch_repo_tree_happy_path_filters_and_writes_tree_file(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    raw_tree = [
        {"path": "src/main.py", "sha": "sha1", "size": 100},
        {"path": "node_modules/foo.js", "sha": "sha2", "size": 50},
        {"path": "image.png", "sha": "sha3", "size": 50},
    ]

    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_tree",
            AsyncMock(return_value=(raw_tree, False)),
        ),
    ):
        result = await fetch_repo_tree(CONNECTION_ID, "proj1", 999, "acme/repo", "main")

    assert result == {"count": 1, "truncated": False}
    out = _tree_path("proj1", CONNECTION_ID)
    assert out.exists()
    assert json.loads(out.read_text()) == [
        {"path": "src/main.py", "sha": "sha1", "size": 100}
    ]


async def test_fetch_repo_tree_reports_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_tree",
            AsyncMock(return_value=([{"path": "a.py", "sha": "s", "size": 1}], True)),
        ),
    ):
        result = await fetch_repo_tree(CONNECTION_ID, "proj1", 999, "acme/repo", "main")

    assert result["truncated"] is True


async def test_fetch_repo_tree_auth_error_raises_non_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_tree",
            AsyncMock(side_effect=gh_client.GithubAuthError("bad token")),
        ),
    ):
        with pytest.raises(ApplicationError) as exc:
            await fetch_repo_tree(CONNECTION_ID, "proj1", 999, "acme/repo", "main")

    assert exc.value.non_retryable is True


async def test_fetch_repo_tree_not_found_raises_non_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_tree",
            AsyncMock(side_effect=gh_client.GithubNotFoundError("no such repo")),
        ),
    ):
        with pytest.raises(ApplicationError) as exc:
            await fetch_repo_tree(CONNECTION_ID, "proj1", 999, "acme/repo", "main")

    assert exc.value.non_retryable is True


async def test_fetch_repo_tree_rate_limit_error_propagates_as_retryable(
    tmp_path, monkeypatch
):
    """GithubRateLimitError/GithubServiceError are deliberately NOT caught
    here — they must propagate as plain exceptions so the workflow's
    retryable _GITHUB_RETRY policy applies, unlike the non-retryable
    Auth/NotFound path above."""
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_tree",
            AsyncMock(side_effect=gh_client.GithubRateLimitError("rate limited")),
        ),
    ):
        with pytest.raises(gh_client.GithubRateLimitError):
            await fetch_repo_tree(CONNECTION_ID, "proj1", 999, "acme/repo", "main")


# ── fetch_file_contents ───────────────────────────────────────────────────────


async def test_fetch_file_contents_happy_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    tree_file = _tree_path("proj1", CONNECTION_ID)
    tree_file.parent.mkdir(parents=True, exist_ok=True)
    tree_file.write_text(
        json.dumps(
            [
                {"path": "a.py", "sha": "sha-a", "size": 10},
                {"path": "b.py", "sha": "sha-b", "size": 10},
            ]
        )
    )
    blobs = {"sha-a": "content a", "sha-b": "content b"}

    async def _get_blob(token, repo, sha):
        return blobs[sha]

    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_blob",
            AsyncMock(side_effect=_get_blob),
        ),
    ):
        count = await _env.run(
            fetch_file_contents, CONNECTION_ID, "proj1", 999, "acme/repo"
        )

    assert count == 2
    assert not tree_file.exists()  # cleaned up on success
    out = _file_chunks_path("proj1", CONNECTION_ID)
    chunks = json.loads(out.read_text())
    assert {c["path"] for c in chunks} == {"a.py", "b.py"}


async def test_fetch_file_contents_missing_tree_file_raises_non_retryable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    with pytest.raises(ApplicationError) as exc:
        await _env.run(fetch_file_contents, CONNECTION_ID, "proj1", 999, "acme/repo")

    assert exc.value.non_retryable is True


async def test_fetch_file_contents_skips_blob_not_found(tmp_path, monkeypatch):
    """A blob deleted between the tree fetch and the blob fetch must be
    silently skipped, not fail the whole activity."""
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    tree_file = _tree_path("proj1", CONNECTION_ID)
    tree_file.parent.mkdir(parents=True, exist_ok=True)
    tree_file.write_text(
        json.dumps(
            [
                {"path": "a.py", "sha": "sha-a", "size": 10},
                {"path": "gone.py", "sha": "sha-missing", "size": 10},
            ]
        )
    )

    async def _get_blob(token, repo, sha):
        if sha == "sha-missing":
            raise gh_client.GithubNotFoundError("deleted mid-sync")
        return "content a"

    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.get_blob",
            AsyncMock(side_effect=_get_blob),
        ),
    ):
        count = await _env.run(
            fetch_file_contents, CONNECTION_ID, "proj1", 999, "acme/repo"
        )

    assert count == 2  # returns len(tree items), regardless of skips
    out = _file_chunks_path("proj1", CONNECTION_ID)
    chunks = json.loads(out.read_text())
    assert [c["path"] for c in chunks] == ["a.py"]


# ── fetch_issues ──────────────────────────────────────────────────────────────


async def test_fetch_issues_happy_path_with_comments(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    # In the real pipeline this directory already exists — fetch_repo_tree
    # (which does mkdir) always runs first. fetch_issues itself doesn't mkdir.
    (tmp_path / "proj1").mkdir(parents=True, exist_ok=True)
    issues = [
        {"number": 1, "title": "Bug", "body": "Something broke", "comments": 1},
        {"number": 2, "title": "Feature", "body": "", "comments": 0},
    ]
    comments = [{"user": {"login": "alice"}, "body": "I can confirm"}]

    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.list_issues",
            AsyncMock(return_value=issues),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.list_issue_comments",
            AsyncMock(return_value=comments),
        ) as mock_comments,
    ):
        count = await _env.run(fetch_issues, CONNECTION_ID, "proj1", 999, "acme/repo")

    assert count == 2
    mock_comments.assert_called_once_with(
        "tok", "acme/repo", 1
    )  # only issue 1 has comments
    out = _issue_chunks_path("proj1", CONNECTION_ID)
    chunks = json.loads(out.read_text())
    assert {c["path"] for c in chunks} == {"issues/1", "issues/2"}
    issue_1_content = next(c["content"] for c in chunks if c["path"] == "issues/1")
    assert "alice: I can confirm" in issue_1_content


async def test_fetch_issues_comments_not_found_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    (tmp_path / "proj1").mkdir(parents=True, exist_ok=True)
    issues = [{"number": 1, "title": "Bug", "body": "x", "comments": 1}]

    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.list_issues",
            AsyncMock(return_value=issues),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.list_issue_comments",
            AsyncMock(side_effect=gh_client.GithubNotFoundError("comments gone")),
        ),
    ):
        count = await _env.run(fetch_issues, CONNECTION_ID, "proj1", 999, "acme/repo")

    assert count == 1
    out = _issue_chunks_path("proj1", CONNECTION_ID)
    chunks = json.loads(out.read_text())
    assert "Comments:" not in chunks[0]["content"]


async def test_fetch_issues_auth_error_raises_non_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    with (
        patch(
            "temporal.activities.github_activities.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "temporal.activities.github_activities.gh_client.list_issues",
            AsyncMock(side_effect=gh_client.GithubAuthError("bad token")),
        ),
    ):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(fetch_issues, CONNECTION_ID, "proj1", 999, "acme/repo")

    assert exc.value.non_retryable is True


# ── clear_existing_vectors_for_repo ──────────────────────────────────────────


async def test_clear_existing_vectors_for_repo_delegates_to_chroma_delete():
    with patch(
        "temporal.activities.github_activities.chroma_delete_by_repo"
    ) as mock_delete:
        await clear_existing_vectors_for_repo("proj1", CONNECTION_ID)

    mock_delete.assert_called_once_with("proj1", CONNECTION_ID)


# ── embed_and_index_github_chunks ────────────────────────────────────────────


async def test_embed_and_index_github_chunks_happy_path(tmp_path, monkeypatch):
    file_out = _write_file_chunks(
        tmp_path,
        monkeypatch,
        "proj1",
        CONNECTION_ID,
        [{"path": "a.py", "chunk_index": 0, "content": "print(1)"}],
    )
    issue_out = _write_issue_chunks(
        tmp_path,
        monkeypatch,
        "proj1",
        CONNECTION_ID,
        [{"path": "issues/1", "chunk_index": 0, "content": "Issue #1: bug"}],
    )
    factory = _embed_factory([[0.1], [0.2]])

    with (
        patch("temporal.activities.github_activities.get_embedding_provider", factory),
        patch("temporal.activities.github_activities.add_chunks") as mock_add,
    ):
        count = await _env.run(
            embed_and_index_github_chunks, CONNECTION_ID, "proj1", "acme/repo"
        )

    assert count == 2
    mock_add.assert_called_once()
    call_args = mock_add.call_args
    assert call_args.args[0] == "proj1"
    chunk_dicts = call_args.args[1]
    assert [c["id"] for c in chunk_dicts] == [
        f"{CONNECTION_ID}:file:a.py:0",
        f"{CONNECTION_ID}:issue:issues/1:0",
    ]
    assert chunk_dicts[0]["metadata"]["source_type"] == "github"
    assert chunk_dicts[0]["metadata"]["ref_type"] == "file"
    assert chunk_dicts[0]["metadata"]["filename"] == "acme/repo:a.py"
    assert chunk_dicts[1]["metadata"]["ref_type"] == "issue"
    assert call_args.args[2] == [[0.1], [0.2]]

    assert not file_out.exists()
    assert not issue_out.exists()


async def test_embed_and_index_github_chunks_retry_produces_identical_ids(
    tmp_path, monkeypatch
):
    """Simulates a Temporal retry: run twice against the same chunks. IDs
    must be identical across runs so add_chunks' upsert overwrites the prior
    attempt instead of duplicating records."""
    chunks = [{"path": "a.py", "chunk_index": 0, "content": "print(1)"}]
    factory = _embed_factory([[0.1]])
    seen_id_batches = []

    def _capture_add(project_id, chunk_dicts, embeddings):
        seen_id_batches.append([c["id"] for c in chunk_dicts])

    for _ in range(2):
        _write_file_chunks(tmp_path, monkeypatch, "proj1", CONNECTION_ID, chunks)
        with (
            patch(
                "temporal.activities.github_activities.get_embedding_provider",
                factory,
            ),
            patch(
                "temporal.activities.github_activities.add_chunks",
                side_effect=_capture_add,
            ),
        ):
            await _env.run(
                embed_and_index_github_chunks, CONNECTION_ID, "proj1", "acme/repo"
            )

    assert len(seen_id_batches) == 2
    assert seen_id_batches[0] == seen_id_batches[1]


async def test_embed_and_index_github_chunks_no_chunks_returns_zero(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "temporal.activities.github_activities.settings.upload_dir", tmp_path
    )
    count = await _env.run(
        embed_and_index_github_chunks, CONNECTION_ID, "proj1", "acme/repo"
    )
    assert count == 0


async def test_embed_and_index_github_chunks_auth_error_keeps_temp_files(
    tmp_path, monkeypatch
):
    file_out = _write_file_chunks(
        tmp_path,
        monkeypatch,
        "proj1",
        CONNECTION_ID,
        [{"path": "a.py", "chunk_index": 0, "content": "x"}],
    )
    provider = MagicMock()
    provider.embed = AsyncMock(side_effect=ProviderAuthError("bad key"))

    with patch(
        "temporal.activities.github_activities.get_embedding_provider",
        MagicMock(return_value=provider),
    ):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(
                embed_and_index_github_chunks, CONNECTION_ID, "proj1", "acme/repo"
            )

    assert exc.value.non_retryable is True
    # Failure happens before cleanup — the chunks file must still be there.
    assert file_out.exists()


async def test_embed_and_index_github_chunks_provider_not_available_raises_non_retryable(
    tmp_path, monkeypatch
):
    _write_file_chunks(
        tmp_path,
        monkeypatch,
        "proj1",
        CONNECTION_ID,
        [{"path": "a.py", "chunk_index": 0, "content": "x"}],
    )
    provider = MagicMock()
    provider.embed = AsyncMock(
        side_effect=ProviderNotAvailableError("unknown provider")
    )

    with patch(
        "temporal.activities.github_activities.get_embedding_provider",
        MagicMock(return_value=provider),
    ):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(
                embed_and_index_github_chunks, CONNECTION_ID, "proj1", "acme/repo"
            )

    assert exc.value.non_retryable is True
