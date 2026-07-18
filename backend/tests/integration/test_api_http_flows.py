"""
BDD-style, black-box API tests: every test only calls real HTTP endpoints
(via the `client` fixture — real FastAPI routing, real request/response
serialization, real in-memory SQLite underneath) and only makes assertions
against the JSON responses those calls return. No test here reaches into
`db_session`, a service module, or the ORM directly — if a test needs to
verify something was persisted, it does that by calling a second (GET)
endpoint, never by inspecting the database.

Each test is written as Given / When / Then. The one exception is Temporal
itself: file upload dispatches a workflow, so `get_temporal_client` is
mocked out (the same seam tests/test_files.py already uses) purely so the
test doesn't need a real worker running — this is a boundary mock for an
external system, not a shortcut around the API under test. Chat message
persistence specifically depends on a workflow activity actually running,
so that round trip is covered separately in test_chat_workflow_integration.py
and test_document_workflow_integration.py, which drive the same real HTTP
endpoints through a real Temporal workflow instead of a mock.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import settings

pytestmark = pytest.mark.integration


def _mock_temporal():
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()
    return patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    )


# ── Projects ──────────────────────────────────────────────────────────────────


async def test_create_project_then_get_returns_the_same_project(client):
    """
    Given no projects exist yet
    When a project is created via POST /api/projects
    Then GET /api/projects/{id} must return exactly what was created
    """
    create_resp = await client.post(
        "/api/projects", json={"name": "Acme", "description": "Acme's docs"}
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Acme"
    assert created["description"] == "Acme's docs"

    get_resp = await client.get(f"/api/projects/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created


async def test_create_project_then_list_includes_it(client):
    """
    Given a project has been created
    When GET /api/projects is called
    Then the created project must appear in the list, unchanged
    """
    created = (await client.post("/api/projects", json={"name": "Acme"})).json()

    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    assert created in list_resp.json()


async def test_delete_project_then_get_returns_404(client):
    """
    Given a project exists
    When it is deleted via DELETE /api/projects/{id}
    Then GET /api/projects/{id} must return 404
    """
    pid = (await client.post("/api/projects", json={"name": "Temp"})).json()["id"]

    with patch("services.project_service.chroma_delete_project"):
        delete_resp = await client.delete(f"/api/projects/{pid}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/projects/{pid}")
    assert get_resp.status_code == 404


# ── Agents ────────────────────────────────────────────────────────────────────


async def test_create_agent_then_get_returns_the_same_agent(client):
    """
    Given a project exists
    When an agent is created under it via POST /api/projects/{id}/agents
    Then GET /api/agents/{id} must return exactly what was created
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]

    create_resp = await client.post(
        f"/api/projects/{pid}/agents",
        json={
            "name": "Support Bot",
            "description": "Handles tickets",
            "system_prompt": "Be concise.",
            "top_k": 6,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()

    get_resp = await client.get(f"/api/agents/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created


async def test_create_agent_then_list_includes_it(client):
    """
    Given two agents have been created under the same project
    When GET /api/projects/{id}/agents is called
    Then both must appear, and only those two
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    a = (await client.post(f"/api/projects/{pid}/agents", json={"name": "A"})).json()
    b = (await client.post(f"/api/projects/{pid}/agents", json={"name": "B"})).json()

    list_resp = await client.get(f"/api/projects/{pid}/agents")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert a in body
    assert b in body
    assert len(body) == 2


async def test_update_agent_then_get_reflects_the_change(client):
    """
    Given an agent exists
    When it is updated via PUT /api/agents/{id}
    Then a fresh GET /api/agents/{id} (not the PUT response) must show the
    new values
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Old Name"})
    ).json()["id"]

    put_resp = await client.put(
        f"/api/agents/{aid}", json={"name": "New Name", "top_k": 9}
    )
    assert put_resp.status_code == 200

    get_resp = await client.get(f"/api/agents/{aid}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["name"] == "New Name"
    assert body["top_k"] == 9


async def test_delete_agent_then_get_returns_404(client):
    """
    Given an agent exists
    When it is deleted via DELETE /api/agents/{id}
    Then GET /api/agents/{id} must return 404
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]

    delete_resp = await client.delete(f"/api/agents/{aid}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/agents/{aid}")
    assert get_resp.status_code == 404


# ── Files ─────────────────────────────────────────────────────────────────────


async def test_upload_file_then_list_includes_its_metadata(client):
    """
    Given a project exists
    When a file is uploaded via POST /api/projects/{id}/files/upload
    Then GET /api/projects/{id}/files must include it, with matching metadata
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]

    with _mock_temporal():
        upload_resp = await client.post(
            f"/api/projects/{pid}/files/upload",
            files={"file": ("report.txt", io.BytesIO(b"hello world"), "text/plain")},
        )
    assert upload_resp.status_code == 201
    created = upload_resp.json()
    assert created["filename"] == "report.txt"
    assert created["size"] == len(b"hello world")
    assert created["chunk_status"] == "pending"

    list_resp = await client.get(f"/api/projects/{pid}/files")
    assert list_resp.status_code == 200
    assert created in list_resp.json()


async def test_delete_file_then_list_no_longer_includes_it(client):
    """
    Given an uploaded file exists
    When it is deleted via DELETE /api/projects/{id}/files/{file_id}
    Then GET /api/projects/{id}/files must no longer include it
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    with _mock_temporal():
        fid = (
            await client.post(
                f"/api/projects/{pid}/files/upload",
                files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
            )
        ).json()["id"]

    with patch("services.project_file_service.chroma_delete_file"):
        delete_resp = await client.delete(f"/api/projects/{pid}/files/{fid}")
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/projects/{pid}/files")
    assert all(f["id"] != fid for f in list_resp.json())


# ── Chat sessions ─────────────────────────────────────────────────────────────


async def test_create_session_then_list_includes_it(client):
    """
    Given an agent exists
    When a chat session is created via POST /api/agents/{id}/sessions
    Then GET /api/agents/{id}/sessions must include it, with a null title
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]

    create_resp = await client.post(f"/api/agents/{aid}/sessions")
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["agent_id"] == aid
    assert created["title"] is None

    list_resp = await client.get(f"/api/agents/{aid}/sessions")
    assert list_resp.status_code == 200
    assert created in list_resp.json()


async def test_new_session_has_no_messages_yet(client):
    """
    Given a freshly created chat session
    When GET /api/sessions/{id}/messages is called
    Then it must return an empty list
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    messages_resp = await client.get(f"/api/sessions/{sid}/messages")
    assert messages_resp.status_code == 200
    assert messages_resp.json() == []


# ── Share links ───────────────────────────────────────────────────────────────


async def test_generate_share_link_then_get_agent_reflects_it(client):
    """
    Given an agent exists
    When a share link is generated via POST /api/agents/{id}/share
    Then GET /api/agents/{id} must show the same share_slug and cap
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]

    share_resp = await client.post(
        f"/api/agents/{aid}/share", json={"daily_message_cap": 25}
    )
    assert share_resp.status_code == 200
    share = share_resp.json()
    assert share["daily_message_cap"] == 25

    get_resp = await client.get(f"/api/agents/{aid}")
    assert get_resp.status_code == 200
    agent = get_resp.json()
    assert agent["share_slug"] == share["share_slug"]
    assert agent["share_daily_message_cap"] == 25


async def test_generate_share_link_then_public_view_is_reachable(client):
    """
    Given a share link has been generated for an agent
    When GET /api/public/agents/{slug} is called
    Then it must return that agent's public-safe view (name/description only)
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(
            f"/api/projects/{pid}/agents",
            json={"name": "Helper", "description": "A helpful bot"},
        )
    ).json()["id"]
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    public_resp = await client.get(f"/api/public/agents/{slug}")
    assert public_resp.status_code == 200
    assert public_resp.json() == {"name": "Helper", "description": "A helpful bot"}


async def test_revoke_share_link_then_public_view_returns_404(client):
    """
    Given a share link exists for an agent
    When it is revoked via DELETE /api/agents/{id}/share
    Then GET /api/agents/{id} must show share_slug=None, and the old public
    URL must 404
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    revoke_resp = await client.delete(f"/api/agents/{aid}/share")
    assert revoke_resp.status_code == 204

    get_resp = await client.get(f"/api/agents/{aid}")
    assert get_resp.json()["share_slug"] is None

    public_resp = await client.get(f"/api/public/agents/{slug}")
    assert public_resp.status_code == 404


async def test_regenerating_share_link_then_get_agent_shows_the_new_slug(client):
    """
    Given an agent already has an active share link
    When the link is regenerated via POST /api/agents/{id}/share
    Then GET /api/agents/{id} must show the new slug, and the old public URL
    must 404
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    old_slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()[
        "share_slug"
    ]

    new_slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()[
        "share_slug"
    ]
    assert new_slug != old_slug

    get_resp = await client.get(f"/api/agents/{aid}")
    assert get_resp.json()["share_slug"] == new_slug
    assert (await client.get(f"/api/public/agents/{old_slug}")).status_code == 404


async def test_generate_share_link_without_cap_then_get_agent_shows_default(client):
    """
    Given an agent exists
    When a share link is generated without an explicit daily cap
    Then GET /api/agents/{id} must show the configured default cap
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]

    await client.post(f"/api/agents/{aid}/share", json={})

    get_resp = await client.get(f"/api/agents/{aid}")
    assert get_resp.json()["share_daily_message_cap"] == (
        settings.share_default_daily_message_cap
    )


# ── Public visitor sessions ───────────────────────────────────────────────────


async def test_public_session_creation_then_public_list_includes_it(client):
    """
    Given a shared agent
    When a visitor creates a session via POST /api/public/agents/{slug}/sessions
    Then GET /api/public/agents/{slug}/sessions must include it
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    create_resp = await client.post(f"/api/public/agents/{slug}/sessions")
    assert create_resp.status_code == 201
    created = create_resp.json()

    list_resp = await client.get(f"/api/public/agents/{slug}/sessions")
    assert list_resp.status_code == 200
    assert created in list_resp.json()


async def test_public_new_session_has_no_messages_yet(client):
    """
    Given a freshly created visitor session
    When GET /api/public/agents/{slug}/sessions/{id}/messages is called
    Then it must return an empty list
    """
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    messages_resp = await client.get(
        f"/api/public/agents/{slug}/sessions/{sid}/messages"
    )
    assert messages_resp.status_code == 200
    assert messages_resp.json() == []
