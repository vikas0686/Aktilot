"""
BDD-style, black-box API tests for /api/agents/{id}/sessions and
/api/sessions/{id}/messages — pure HTTP in, JSON out, no db_session/service
pokes. See test_bdd_projects.py for the shared rationale.

Message *content* round trips (a real chat message actually landing in the
DB) require a workflow activity to run, so that's covered separately in
test_chat_workflow_integration.py. This file only covers what's reachable
through the session/message CRUD endpoints themselves: creating sessions,
listing them, and reading (empty) message lists.
"""

import pytest

pytestmark = pytest.mark.integration


async def _create_project_and_agent(client) -> tuple[str, str]:
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    return pid, aid


# ── Create session ────────────────────────────────────────────────────────────


async def test_create_session_succeeds_with_null_title(client):
    """
    Given an agent exists
    When a session is created via POST /api/agents/{id}/sessions
    Then it has a null title and matches the agent
    """
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/sessions")
    assert r.status_code == 201
    body = r.json()
    assert body["agent_id"] == aid
    assert body["title"] is None
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_session_agent_not_found_returns_404(client):
    r = await client.post("/api/agents/00000000-0000-0000-0000-000000000000/sessions")
    assert r.status_code == 404


async def test_create_session_malformed_agent_uuid_returns_422(client):
    r = await client.post("/api/agents/not-a-uuid/sessions")
    assert r.status_code == 422


async def test_create_two_sessions_for_same_agent_get_distinct_ids(client):
    _, aid = await _create_project_and_agent(client)
    a = (await client.post(f"/api/agents/{aid}/sessions")).json()
    b = (await client.post(f"/api/agents/{aid}/sessions")).json()
    assert a["id"] != b["id"]


async def test_create_session_for_deleted_agent_returns_404(client):
    _, aid = await _create_project_and_agent(client)
    await client.delete(f"/api/agents/{aid}")
    r = await client.post(f"/api/agents/{aid}/sessions")
    assert r.status_code == 404


# ── List sessions ─────────────────────────────────────────────────────────────


async def test_list_sessions_for_agent_with_none_returns_empty(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.get(f"/api/agents/{aid}/sessions")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_sessions_agent_not_found_returns_404(client):
    r = await client.get("/api/agents/00000000-0000-0000-0000-000000000000/sessions")
    assert r.status_code == 404


async def test_list_sessions_malformed_agent_uuid_returns_422(client):
    r = await client.get("/api/agents/not-a-uuid/sessions")
    assert r.status_code == 422


async def test_list_sessions_returns_the_one_created(client):
    _, aid = await _create_project_and_agent(client)
    created = (await client.post(f"/api/agents/{aid}/sessions")).json()

    r = await client.get(f"/api/agents/{aid}/sessions")
    assert r.status_code == 200
    assert r.json() == [created]


async def test_list_sessions_returns_only_this_agents_sessions(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    a1 = (await client.post(f"/api/projects/{pid}/agents", json={"name": "A1"})).json()[
        "id"
    ]
    a2 = (await client.post(f"/api/projects/{pid}/agents", json={"name": "A2"})).json()[
        "id"
    ]
    s1 = (await client.post(f"/api/agents/{a1}/sessions")).json()
    s2 = (await client.post(f"/api/agents/{a1}/sessions")).json()
    await client.post(f"/api/agents/{a2}/sessions")

    r = await client.get(f"/api/agents/{a1}/sessions")
    body = r.json()
    assert len(body) == 2
    assert {s["id"] for s in body} == {s1["id"], s2["id"]}


async def test_list_sessions_orders_most_recently_updated_first(client):
    """Freshly created, never-touched sessions: most-recently-created is
    also most-recently-updated, so this proves the ORDER BY updated_at DESC
    without needing a real chat message to bump it."""
    _, aid = await _create_project_and_agent(client)
    first = (await client.post(f"/api/agents/{aid}/sessions")).json()
    second = (await client.post(f"/api/agents/{aid}/sessions")).json()
    third = (await client.post(f"/api/agents/{aid}/sessions")).json()

    r = await client.get(f"/api/agents/{aid}/sessions")
    ids = [s["id"] for s in r.json()]
    assert ids == [third["id"], second["id"], first["id"]]


# ── Session messages ──────────────────────────────────────────────────────────


async def test_new_session_has_no_messages(client):
    _, aid = await _create_project_and_agent(client)
    sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    r = await client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_messages_for_unknown_session_returns_404(client):
    r = await client.get("/api/sessions/00000000-0000-0000-0000-000000000000/messages")
    assert r.status_code == 404


async def test_messages_malformed_session_uuid_returns_422(client):
    r = await client.get("/api/sessions/not-a-uuid/messages")
    assert r.status_code == 422


async def test_messages_for_deleted_session_returns_404(client):
    """Deleting the parent agent cascades away its sessions."""
    _, aid = await _create_project_and_agent(client)
    sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]
    await client.delete(f"/api/agents/{aid}")

    r = await client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 404


async def test_agent_messages_endpoint_empty_for_new_agent(client):
    """GET /api/agents/{id}/messages (all messages across all of an agent's
    sessions) — also empty until a real chat message is ever persisted."""
    _, aid = await _create_project_and_agent(client)
    r = await client.get(f"/api/agents/{aid}/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_agent_messages_endpoint_not_found_for_unknown_agent(client):
    r = await client.get("/api/agents/00000000-0000-0000-0000-000000000000/messages")
    assert r.status_code == 404
