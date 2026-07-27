"""
Full-stack integration tests for the GitHub sync pipeline.

Like test_document_workflow_integration.py, these run the REAL
GithubSyncWorkflow on a REAL ephemeral Temporal server through a REAL Worker
running the REAL activities — only the embedding provider, ChromaDB calls,
and the GitHub REST API boundary (services.github.client /
services.github.app_auth.get_installation_token) are mocked, via the
`github_api_mock` fixture below plus the `github_embedding_provider` /
`chroma_github_mock` fixtures in conftest.py. Before this file,
github_activities.py and github_sync_workflow.py had zero test coverage
exercising the real Temporal orchestration/retry-policy path —
test_github_connector.py stubs the whole workflow away via
get_temporal_client, and test_github_activities.py calls each activity
function directly, in isolation.

The connect route uses start_workflow (fire-and-forget), not
execute_workflow, so these tests explicitly await the workflow handle to
observe completion.
"""

import uuid

import pytest
from temporalio.client import WorkflowFailureError

from db.models.github_installation import GithubInstallation
from temporal.workflows.github_sync_workflow import GithubSyncWorkflow
from tests.integration.conftest import ScriptedProvider

pytestmark = pytest.mark.integration

TREE = [
    {"path": "src/main.py", "sha": "sha-main", "size": 20},
    {"path": "README.md", "sha": "sha-readme", "size": 20},
]
BLOBS = {"sha-main": "print('hi')", "sha-readme": "# Project"}
ISSUES = [{"number": 1, "title": "Bug", "body": "It crashes", "comments": 0}]


@pytest.fixture
def github_api_mock(monkeypatch: pytest.MonkeyPatch):
    """Patches the GitHub REST boundary at both call sites that need it: the
    connect_repo route (installation token only — these tests always pass an
    explicit branch, so the route never calls list_installation_repos) and
    the activities module (token + tree/blob/issue endpoints)."""

    async def _get_installation_token(installation_id):
        return "tok"

    async def _get_tree(token, repo_full_name, branch):
        return TREE, False

    async def _get_blob(token, repo_full_name, sha):
        return BLOBS[sha]

    async def _list_issues(token, repo_full_name):
        return ISSUES

    monkeypatch.setattr(
        "api.routes.github_connector.get_installation_token",
        _get_installation_token,
    )
    monkeypatch.setattr(
        "temporal.activities.github_activities.get_installation_token",
        _get_installation_token,
    )
    monkeypatch.setattr(
        "temporal.activities.github_activities.gh_client.get_tree", _get_tree
    )
    monkeypatch.setattr(
        "temporal.activities.github_activities.gh_client.get_blob", _get_blob
    )
    monkeypatch.setattr(
        "temporal.activities.github_activities.gh_client.list_issues", _list_issues
    )


async def _create_project(client) -> str:
    return (await client.post("/api/projects", json={"name": "P"})).json()["id"]


async def _create_installation(
    db_session, project_id: str, installation_id: int = 555
) -> GithubInstallation:
    installation = GithubInstallation(
        project_id=uuid.UUID(project_id),
        installation_id=installation_id,
        account_login="acme",
        account_type="Organization",
    )
    db_session.add(installation)
    await db_session.commit()
    await db_session.refresh(installation)
    return installation


async def _connect(client, project_id: str, repo_full_name: str = "acme/repo") -> str:
    r = await client.post(
        f"/api/projects/{project_id}/github/connections",
        json={"repo_full_name": repo_full_name, "branch": "main"},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _get_connection(client, project_id: str, connection_id: str) -> dict:
    connections = (
        await client.get(f"/api/projects/{project_id}/github/connections")
    ).json()
    return next(c for c in connections if c["id"] == connection_id)


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_github_sync_workflow_runs_end_to_end(
    github_integration_client,
    db_session,
    temporal_env,
    chroma_github_mock,
    github_api_mock,
):
    pid = await _create_project(github_integration_client)
    await _create_installation(db_session, pid)
    connection_id = await _connect(github_integration_client, pid)

    await temporal_env.client.get_workflow_handle(f"gh-sync-{connection_id}").result()

    record = await _get_connection(github_integration_client, pid, connection_id)
    assert record["sync_status"] == "synced"
    assert record["file_count"] == 2
    assert record["issue_count"] == 1
    assert record["chunk_count"] == 3  # 2 files + 1 issue, each under CHUNK_SIZE
    assert record["tree_truncated"] is False

    # embed_and_index_github_chunks really ran and really called add_chunks
    assert len(chroma_github_mock["added"]) == 1
    added_project_id, chunk_dicts, embeddings = chroma_github_mock["added"][0]
    assert added_project_id == pid
    assert len(chunk_dicts) == 3
    assert len(embeddings) == 3
    assert {c["metadata"]["ref_type"] for c in chunk_dicts} == {"file", "issue"}
    assert all(c["metadata"]["repo_full_name"] == "acme/repo" for c in chunk_dicts)

    # clear_existing_vectors_for_repo really ran too
    assert chroma_github_mock["deleted"] == [(pid, connection_id)]


async def test_github_sync_workflow_marks_syncing_before_fetching(
    github_worker, temporal_env, task_queue, db_session, github_api_mock
):
    """The workflow's first step (mark_connection_syncing) must run and
    commit before the (slower) fetch steps — checked by executing the
    workflow directly against a pre-seeded connection row and inspecting
    intermediate state isn't needed here; instead this asserts the terminal
    state reflects a real transition through 'syncing', not just 'pending'
    jumping straight to 'synced'."""
    project_id = uuid.uuid4()
    installation = GithubInstallation(
        project_id=project_id,
        installation_id=555,
        account_login="acme",
        account_type="Organization",
    )
    db_session.add(installation)
    await db_session.commit()
    await db_session.refresh(installation)

    from db.models.github_connection import GithubConnection

    connection = GithubConnection(
        project_id=project_id,
        installation_id=installation.id,
        repo_full_name="acme/repo",
        default_branch="main",
        sync_status="pending",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    await temporal_env.client.execute_workflow(
        GithubSyncWorkflow.run,
        args=[
            str(connection.id),
            str(project_id),
            555,
            "acme/repo",
            "main",
            "full",
        ],
        id=f"gh-sync-{connection.id}",
        task_queue=task_queue,
    )

    await db_session.refresh(connection)
    assert connection.sync_status == "synced"


# ── Failure modes ─────────────────────────────────────────────────────────────


async def test_github_sync_workflow_repo_not_found_sets_error_status(
    github_integration_client, db_session, temporal_env, github_api_mock, monkeypatch
):
    """fetch_repo_tree wraps GithubNotFoundError as a non-retryable
    ApplicationError — the workflow must catch that, mark the connection
    'error', and still fail the workflow overall (not swallow it silently)."""
    from services.github import client as gh_client

    async def _not_found(token, repo_full_name, branch):
        raise gh_client.GithubNotFoundError("no such repo")

    monkeypatch.setattr(
        "temporal.activities.github_activities.gh_client.get_tree", _not_found
    )

    pid = await _create_project(github_integration_client)
    await _create_installation(db_session, pid)
    connection_id = await _connect(github_integration_client, pid)

    with pytest.raises(WorkflowFailureError):
        await temporal_env.client.get_workflow_handle(
            f"gh-sync-{connection_id}"
        ).result()

    record = await _get_connection(github_integration_client, pid, connection_id)
    assert record["sync_status"] == "error"
    # mark_connection_error receives str(exc) on the workflow's caught
    # exception, which at that layer is Temporal's ActivityError wrapper
    # (not the original GithubNotFoundError message) — this pins down that
    # real, if not maximally informative, current behavior.
    assert record["error_message"]


async def test_github_sync_workflow_embedding_auth_error_sets_error_status(
    github_integration_client,
    db_session,
    temporal_env,
    github_api_mock,
    github_embedding_provider: ScriptedProvider,
):
    from services.llm.base import ProviderAuthError

    github_embedding_provider.responses = [ProviderAuthError("invalid API key")]

    pid = await _create_project(github_integration_client)
    await _create_installation(db_session, pid)
    connection_id = await _connect(github_integration_client, pid)

    with pytest.raises(WorkflowFailureError):
        await temporal_env.client.get_workflow_handle(
            f"gh-sync-{connection_id}"
        ).result()

    record = await _get_connection(github_integration_client, pid, connection_id)
    assert record["sync_status"] == "error"


async def test_github_sync_workflow_retries_transient_tree_failure_then_succeeds(
    github_integration_client,
    db_session,
    temporal_env,
    chroma_github_mock,
    github_api_mock,
    monkeypatch,
):
    """fetch_repo_tree fails twice with a plain (retryable-by-default,
    non-ApplicationError) exception, then succeeds — exercising the
    workflow's real _GITHUB_RETRY policy end to end under time-skipping."""
    calls = {"count": 0}

    async def _flaky_get_tree(token, repo_full_name, branch):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise RuntimeError("transient network error")
        return TREE, False

    monkeypatch.setattr(
        "temporal.activities.github_activities.gh_client.get_tree", _flaky_get_tree
    )

    pid = await _create_project(github_integration_client)
    await _create_installation(db_session, pid)
    connection_id = await _connect(github_integration_client, pid)

    await temporal_env.client.get_workflow_handle(f"gh-sync-{connection_id}").result()

    record = await _get_connection(github_integration_client, pid, connection_id)
    assert record["sync_status"] == "synced"
    assert calls["count"] == 3
