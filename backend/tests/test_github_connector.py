"""
Unit tests for api/routes/github_connector.py.

Mirrors test_files.py's approach: the Temporal workflow is stubbed out via
get_temporal_client (never runs for real — see
tests/integration/test_github_sync_workflow_integration.py for that), and the
GitHub REST API boundary (services.github.client / services.github.app_auth)
is patched at the function level, matching the codebase's existing convention
for external-service seams (e.g. get_embedding_provider in
test_document_activities.py). No HTTP-transport-level mocking (respx etc.) is
used anywhere in this suite, so none is introduced here either.

Installation/connection DB rows are seeded directly via db_session (as
test_pagination.py's github test already does) for tests that aren't
specifically exercising the install/callback flow itself.
"""

import hashlib
import hmac
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from temporalio.exceptions import WorkflowAlreadyStartedError

from api.routes.github_connector import _sign_state, _verify_state
from db.models.github_connection import GithubConnection
from db.models.github_installation import GithubInstallation


def _configure_github_app(monkeypatch, slug="acme-app", state_secret="s3cret"):
    monkeypatch.setattr("config.settings.github_app_slug", slug)
    monkeypatch.setattr("config.settings.github_app_state_secret", state_secret)


def _make_state(secret: str, project_id: str, expires_at: int) -> str:
    payload = f"{project_id}.{expires_at}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _mock_temporal():
    """Patch for get_temporal_client whose start_workflow is a no-op AsyncMock
    — the context value is the patched AsyncMock itself, so callers wanting to
    assert on start_workflow reach it via `<ctx>.return_value.start_workflow`."""
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()
    return patch(
        "api.routes.github_connector.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    )


async def _create_project(client, name: str = "P") -> str:
    return (await client.post("/api/projects", json={"name": name})).json()["id"]


async def _create_installation(
    db_session,
    project_id: str,
    installation_id: int = 12345,
    account_login: str = "acme",
    account_type: str = "Organization",
) -> GithubInstallation:
    installation = GithubInstallation(
        project_id=uuid.UUID(project_id),
        installation_id=installation_id,
        account_login=account_login,
        account_type=account_type,
    )
    db_session.add(installation)
    await db_session.commit()
    await db_session.refresh(installation)
    return installation


async def _create_connection(
    db_session,
    project_id: str,
    installation: GithubInstallation,
    repo_full_name: str = "acme/repo",
    default_branch: str = "main",
    sync_status: str = "synced",
) -> GithubConnection:
    connection = GithubConnection(
        project_id=uuid.UUID(project_id),
        installation_id=installation.id,
        repo_full_name=repo_full_name,
        default_branch=default_branch,
        sync_status=sync_status,
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)
    return connection


# ── _sign_state / _verify_state ──────────────────────────────────────────────


def test_sign_and_verify_state_roundtrip(monkeypatch):
    _configure_github_app(monkeypatch)
    project_id = str(uuid.uuid4())
    state = _sign_state(project_id)
    assert _verify_state(state) == uuid.UUID(project_id)


def test_verify_state_malformed_raises_400(monkeypatch):
    _configure_github_app(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _verify_state("not-a-valid-state")
    assert exc.value.status_code == 400
    assert "Invalid state parameter" in exc.value.detail


def test_verify_state_tampered_signature_raises_400(monkeypatch):
    _configure_github_app(monkeypatch)
    state = _sign_state(str(uuid.uuid4()))
    tampered = state[:-1] + ("0" if state[-1] != "0" else "1")
    with pytest.raises(HTTPException) as exc:
        _verify_state(tampered)
    assert exc.value.status_code == 400
    assert "Invalid state signature" in exc.value.detail


def test_verify_state_expired_raises_400(monkeypatch):
    _configure_github_app(monkeypatch, state_secret="s3cret")
    expired_state = _make_state("s3cret", str(uuid.uuid4()), int(time.time()) - 10)
    with pytest.raises(HTTPException) as exc:
        _verify_state(expired_state)
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail


# ── GET .../github/install-url ───────────────────────────────────────────────


async def test_install_url_not_configured_returns_503(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/github/install-url")
    assert r.status_code == 503


async def test_install_url_project_not_found_returns_404(client):
    r = await client.get(f"/api/projects/{uuid.uuid4()}/github/install-url")
    assert r.status_code == 404


async def test_install_url_happy_path(client, monkeypatch):
    _configure_github_app(monkeypatch, slug="acme-app", state_secret="s3cret")
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/github/install-url")
    assert r.status_code == 200
    url = r.json()["install_url"]
    assert url.startswith("https://github.com/apps/acme-app/installations/new?state=")


# ── GET /api/github/install/callback ─────────────────────────────────────────


async def test_callback_not_configured_returns_503(client):
    r = await client.get(
        "/api/github/install/callback",
        params={"state": "irrelevant"},
        follow_redirects=False,
    )
    assert r.status_code == 503


async def test_callback_invalid_state_returns_400(client, monkeypatch):
    _configure_github_app(monkeypatch)
    r = await client.get(
        "/api/github/install/callback",
        params={"state": "garbage"},
        follow_redirects=False,
    )
    assert r.status_code == 400


async def test_callback_pending_when_org_install_awaiting_approval(client, monkeypatch):
    _configure_github_app(monkeypatch)
    pid = await _create_project(client)
    state = _sign_state(pid)

    r = await client.get(
        "/api/github/install/callback",
        params={"state": state, "setup_action": "request"},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "github=pending" in r.headers["location"]


async def test_callback_unknown_setup_action_redirects_error(client, monkeypatch):
    _configure_github_app(monkeypatch)
    pid = await _create_project(client)
    state = _sign_state(pid)

    r = await client.get(
        "/api/github/install/callback",
        params={"state": state, "setup_action": "bogus"},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "github=error" in r.headers["location"]


async def test_callback_install_success_upserts_installation(client, monkeypatch):
    _configure_github_app(monkeypatch)
    pid = await _create_project(client)
    state = _sign_state(pid)

    with patch(
        "api.routes.github_connector.gh_client.get_installation",
        AsyncMock(return_value={"account": {"login": "acme", "type": "Organization"}}),
    ):
        r = await client.get(
            "/api/github/install/callback",
            params={"state": state, "setup_action": "install", "installation_id": 42},
            follow_redirects=False,
        )
    assert r.status_code == 307
    assert "github=connected" in r.headers["location"]

    check = await client.get(f"/api/projects/{pid}/github/installation")
    assert check.status_code == 200
    body = check.json()
    assert body["account_login"] == "acme"
    assert body["account_type"] == "Organization"


async def test_callback_install_get_installation_failure_falls_back_to_unknown(
    client, monkeypatch
):
    _configure_github_app(monkeypatch)
    pid = await _create_project(client)
    state = _sign_state(pid)

    with patch(
        "api.routes.github_connector.gh_client.get_installation",
        AsyncMock(side_effect=RuntimeError("github down")),
    ):
        r = await client.get(
            "/api/github/install/callback",
            params={"state": state, "setup_action": "install", "installation_id": 42},
            follow_redirects=False,
        )
    assert r.status_code == 307
    assert "github=connected" in r.headers["location"]

    check = await client.get(f"/api/projects/{pid}/github/installation")
    body = check.json()
    assert body["account_login"] == "unknown"
    assert body["account_type"] == "unknown"


# ── GET .../github/installation ──────────────────────────────────────────────


async def test_get_installation_status_not_found(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/github/installation")
    assert r.status_code == 404


async def test_get_installation_status_happy_path(client, db_session):
    pid = await _create_project(client)
    await _create_installation(
        db_session, pid, account_login="acme", account_type="Organization"
    )
    r = await client.get(f"/api/projects/{pid}/github/installation")
    assert r.status_code == 200
    body = r.json()
    assert body["account_login"] == "acme"
    assert body["account_type"] == "Organization"


# ── GET .../available-installations & POST .../attach-installation ──────────


async def test_available_installations_excludes_own_and_deduplicates(
    client, db_session
):
    pid_a = await _create_project(client, "A")
    pid_b = await _create_project(client, "B")
    pid_c = await _create_project(client, "C")

    # B and C share the same real GitHub installation_id (multi-project reuse)
    await _create_installation(
        db_session, pid_b, installation_id=999, account_login="shared"
    )
    await _create_installation(
        db_session, pid_c, installation_id=999, account_login="shared"
    )
    # A has its own installation — must never see itself listed as reusable
    await _create_installation(
        db_session, pid_a, installation_id=111, account_login="self"
    )

    r = await client.get(f"/api/projects/{pid_a}/github/available-installations")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["installation_id"] == 999
    assert body[0]["account_login"] == "shared"


async def test_attach_installation_not_found_returns_404(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/github/attach-installation",
        json={"installation_id": 999},
    )
    assert r.status_code == 404


async def test_attach_installation_links_existing_installation(client, db_session):
    pid_a = await _create_project(client, "A")
    pid_b = await _create_project(client, "B")
    await _create_installation(
        db_session, pid_b, installation_id=999, account_login="shared"
    )

    r = await client.post(
        f"/api/projects/{pid_a}/github/attach-installation",
        json={"installation_id": 999},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == pid_a
    assert body["account_login"] == "shared"

    check = await client.get(f"/api/projects/{pid_a}/github/installation")
    assert check.status_code == 200


# ── DELETE .../github/installation ───────────────────────────────────────────


async def test_disconnect_installation_not_found_returns_404(client):
    pid = await _create_project(client)
    r = await client.delete(f"/api/projects/{pid}/github/installation")
    assert r.status_code == 404


async def test_disconnect_installation_uninstalls_when_not_shared(client, db_session):
    pid = await _create_project(client)
    installation = await _create_installation(db_session, pid, installation_id=555)
    connection = await _create_connection(db_session, pid, installation)

    with (
        patch("api.routes.github_connector.chroma_delete_by_repo") as mock_chroma,
        patch(
            "api.routes.github_connector.gh_client.uninstall_app", AsyncMock()
        ) as mock_uninstall,
    ):
        r = await client.delete(f"/api/projects/{pid}/github/installation")

    assert r.status_code == 204
    mock_chroma.assert_called_once_with(pid, str(connection.id))
    mock_uninstall.assert_called_once_with(555)

    check = await client.get(f"/api/projects/{pid}/github/installation")
    assert check.status_code == 404


async def test_disconnect_installation_skips_uninstall_when_shared(client, db_session):
    pid_a = await _create_project(client, "A")
    pid_b = await _create_project(client, "B")
    await _create_installation(db_session, pid_a, installation_id=777)
    await _create_installation(db_session, pid_b, installation_id=777)

    with (
        patch("api.routes.github_connector.chroma_delete_by_repo"),
        patch(
            "api.routes.github_connector.gh_client.uninstall_app", AsyncMock()
        ) as mock_uninstall,
    ):
        r = await client.delete(f"/api/projects/{pid_a}/github/installation")

    assert r.status_code == 204
    mock_uninstall.assert_not_called()

    # Project B's link to the shared installation must survive untouched.
    check_b = await client.get(f"/api/projects/{pid_b}/github/installation")
    assert check_b.status_code == 200


async def test_disconnect_installation_github_uninstall_failure_is_non_fatal(
    client, db_session
):
    pid = await _create_project(client)
    await _create_installation(db_session, pid, installation_id=555)

    with (
        patch("api.routes.github_connector.chroma_delete_by_repo"),
        patch(
            "api.routes.github_connector.gh_client.uninstall_app",
            AsyncMock(side_effect=RuntimeError("github down")),
        ),
    ):
        r = await client.delete(f"/api/projects/{pid}/github/installation")

    assert r.status_code == 204
    check = await client.get(f"/api/projects/{pid}/github/installation")
    assert check.status_code == 404


# ── GET .../available-repos ──────────────────────────────────────────────────


async def test_available_repos_requires_installation_returns_404(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/github/available-repos")
    assert r.status_code == 404


async def test_available_repos_filters_already_connected(client, db_session):
    pid = await _create_project(client)
    installation = await _create_installation(db_session, pid)
    await _create_connection(
        db_session, pid, installation, repo_full_name="acme/already-connected"
    )

    with (
        patch(
            "api.routes.github_connector.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "api.routes.github_connector.gh_client.list_installation_repos",
            AsyncMock(
                return_value=[
                    {
                        "full_name": "acme/already-connected",
                        "default_branch": "main",
                        "private": False,
                    },
                    {
                        "full_name": "acme/new-repo",
                        "default_branch": "main",
                        "private": True,
                    },
                ]
            ),
        ),
    ):
        r = await client.get(f"/api/projects/{pid}/github/available-repos")

    assert r.status_code == 200
    assert [repo["full_name"] for repo in r.json()] == ["acme/new-repo"]


# ── POST .../github/connections ──────────────────────────────────────────────


async def test_connect_repo_requires_installation_returns_404(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/github/connections",
        json={"repo_full_name": "acme/repo", "branch": "main"},
    )
    assert r.status_code == 404


async def test_connect_repo_resolves_default_branch_when_omitted(client, db_session):
    pid = await _create_project(client)
    await _create_installation(db_session, pid)

    with (
        patch(
            "api.routes.github_connector.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "api.routes.github_connector.gh_client.list_installation_repos",
            AsyncMock(
                return_value=[
                    {
                        "full_name": "acme/repo",
                        "default_branch": "develop",
                        "private": False,
                    }
                ]
            ),
        ),
        _mock_temporal() as mock_get_client,
    ):
        r = await client.post(
            f"/api/projects/{pid}/github/connections",
            json={"repo_full_name": "acme/repo"},
        )

    assert r.status_code == 201
    body = r.json()
    assert body["default_branch"] == "develop"
    assert body["sync_status"] == "pending"

    mock_client = mock_get_client.return_value
    mock_client.start_workflow.assert_called_once()
    call = mock_client.start_workflow.call_args
    assert call.kwargs["id"] == f"gh-sync-{body['id']}"
    assert call.kwargs["args"][-1] == "full"


async def test_connect_repo_uses_explicit_branch_without_listing_repos(
    client, db_session
):
    pid = await _create_project(client)
    await _create_installation(db_session, pid)

    with (
        patch(
            "api.routes.github_connector.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "api.routes.github_connector.gh_client.list_installation_repos",
            AsyncMock(),
        ) as mock_list_repos,
        _mock_temporal(),
    ):
        r = await client.post(
            f"/api/projects/{pid}/github/connections",
            json={"repo_full_name": "acme/repo", "branch": "release"},
        )

    assert r.status_code == 201
    assert r.json()["default_branch"] == "release"
    mock_list_repos.assert_not_called()


async def test_connect_repo_not_accessible_returns_404(client, db_session):
    pid = await _create_project(client)
    await _create_installation(db_session, pid)

    with (
        patch(
            "api.routes.github_connector.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "api.routes.github_connector.gh_client.list_installation_repos",
            AsyncMock(
                return_value=[
                    {
                        "full_name": "other/repo",
                        "default_branch": "main",
                        "private": False,
                    }
                ]
            ),
        ),
    ):
        r = await client.post(
            f"/api/projects/{pid}/github/connections",
            json={"repo_full_name": "acme/repo"},
        )

    assert r.status_code == 404


async def test_connect_repo_duplicate_returns_409(client, db_session):
    pid = await _create_project(client)
    installation = await _create_installation(db_session, pid)
    await _create_connection(db_session, pid, installation, repo_full_name="acme/repo")

    with patch(
        "api.routes.github_connector.get_installation_token",
        AsyncMock(return_value="tok"),
    ):
        r = await client.post(
            f"/api/projects/{pid}/github/connections",
            json={"repo_full_name": "acme/repo", "branch": "main"},
        )

    assert r.status_code == 409


async def test_connect_repo_workflow_start_failure_marks_error_and_returns_502(
    client, db_session
):
    pid = await _create_project(client)
    await _create_installation(db_session, pid)

    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock(side_effect=RuntimeError("temporal down"))

    with (
        patch(
            "api.routes.github_connector.get_installation_token",
            AsyncMock(return_value="tok"),
        ),
        patch(
            "api.routes.github_connector.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        r = await client.post(
            f"/api/projects/{pid}/github/connections",
            json={"repo_full_name": "acme/repo", "branch": "main"},
        )

    assert r.status_code == 502
    connections = (await client.get(f"/api/projects/{pid}/github/connections")).json()
    assert connections[0]["sync_status"] == "error"
    assert "Failed to start" in connections[0]["error_message"]


# ── POST .../connections/{id}/sync ───────────────────────────────────────────


async def test_sync_connection_not_found_returns_404(client, db_session):
    pid = await _create_project(client)
    await _create_installation(db_session, pid)
    r = await client.post(f"/api/projects/{pid}/github/connections/{uuid.uuid4()}/sync")
    assert r.status_code == 404


async def test_sync_connection_starts_refresh_workflow(client, db_session):
    pid = await _create_project(client)
    installation = await _create_installation(db_session, pid)
    connection = await _create_connection(db_session, pid, installation)

    with _mock_temporal() as mock_get_client:
        r = await client.post(
            f"/api/projects/{pid}/github/connections/{connection.id}/sync"
        )

    assert r.status_code == 200
    assert r.json()["sync_status"] == "pending"

    mock_client = mock_get_client.return_value
    mock_client.start_workflow.assert_called_once()
    call = mock_client.start_workflow.call_args
    assert call.kwargs["id"] == f"gh-sync-{connection.id}"
    assert call.kwargs["args"][-1] == "refresh"


async def test_sync_connection_already_in_progress_returns_409(client, db_session):
    pid = await _create_project(client)
    installation = await _create_installation(db_session, pid)
    connection = await _create_connection(
        db_session, pid, installation, sync_status="syncing"
    )

    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock(
        side_effect=WorkflowAlreadyStartedError(
            workflow_id=f"gh-sync-{connection.id}", workflow_type="GithubSyncWorkflow"
        )
    )
    with patch(
        "api.routes.github_connector.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        r = await client.post(
            f"/api/projects/{pid}/github/connections/{connection.id}/sync"
        )

    assert r.status_code == 409


# ── DELETE .../connections/{id} ───────────────────────────────────────────────


async def test_disconnect_repo_not_found_returns_404(client):
    pid = await _create_project(client)
    r = await client.delete(f"/api/projects/{pid}/github/connections/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_disconnect_repo_removes_it(client, db_session):
    pid = await _create_project(client)
    installation = await _create_installation(db_session, pid)
    connection = await _create_connection(db_session, pid, installation)

    with patch(
        "services.github_connection_service.chroma_delete_by_repo"
    ) as mock_delete:
        r = await client.delete(
            f"/api/projects/{pid}/github/connections/{connection.id}"
        )

    assert r.status_code == 204
    mock_delete.assert_called_once_with(pid, str(connection.id))

    remaining = (await client.get(f"/api/projects/{pid}/github/connections")).json()
    assert remaining == []
