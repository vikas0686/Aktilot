"""
BDD-style, black-box API tests for the public/anonymous-visitor routes
(/api/public/agents/{slug}/sessions, /messages) — pure HTTP in, JSON out,
no db_session/service pokes. See test_bdd_projects.py for the shared
rationale.

"Different visitor" is simulated by clearing the client's cookie jar before
a request — the visitor-id cookie is httpOnly and issued by the server on
first contact (api/public_deps.py), so clearing it and requesting again is
indistinguishable, from the server's point of view, from a new browser.
"""

import pytest

pytestmark = pytest.mark.integration


async def _create_shared_agent(client, **agent_overrides) -> tuple[str, str]:
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    payload = {"name": "Helper"}
    payload.update(agent_overrides)
    aid = (await client.post(f"/api/projects/{pid}/agents", json=payload)).json()["id"]
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]
    return aid, slug


# ── Create visitor session ────────────────────────────────────────────────────


async def test_create_public_session_succeeds(client):
    """
    Given a shared agent
    When a visitor creates a session via POST /api/public/agents/{slug}/sessions
    Then it gets a session tied to that agent, with a null title
    """
    aid, slug = await _create_shared_agent(client)
    r = await client.post(f"/api/public/agents/{slug}/sessions")
    assert r.status_code == 201
    body = r.json()
    assert body["agent_id"] == aid
    assert body["title"] is None


async def test_create_public_session_unknown_slug_returns_404(client):
    r = await client.post("/api/public/agents/does-not-exist/sessions")
    assert r.status_code == 404


async def test_create_public_session_revoked_slug_returns_404(client):
    aid, slug = await _create_shared_agent(client)
    await client.delete(f"/api/agents/{aid}/share")

    r = await client.post(f"/api/public/agents/{slug}/sessions")
    assert r.status_code == 404


async def test_create_public_session_sets_a_visitor_cookie(client):
    aid, slug = await _create_shared_agent(client)
    client.cookies.clear()
    r = await client.post(f"/api/public/agents/{slug}/sessions")
    assert r.status_code == 201
    assert "aktilot_vid" in r.cookies


async def test_visitor_can_create_multiple_sessions_with_same_agent(client):
    _, slug = await _create_shared_agent(client)
    a = (await client.post(f"/api/public/agents/{slug}/sessions")).json()
    b = (await client.post(f"/api/public/agents/{slug}/sessions")).json()
    assert a["id"] != b["id"]


# ── List visitor sessions ─────────────────────────────────────────────────────


async def test_list_public_sessions_when_none_returns_empty(client):
    _, slug = await _create_shared_agent(client)
    r = await client.get(f"/api/public/agents/{slug}/sessions")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_public_sessions_unknown_slug_returns_404(client):
    r = await client.get("/api/public/agents/does-not-exist/sessions")
    assert r.status_code == 404


async def test_list_public_sessions_returns_the_one_created(client):
    _, slug = await _create_shared_agent(client)
    created = (await client.post(f"/api/public/agents/{slug}/sessions")).json()

    r = await client.get(f"/api/public/agents/{slug}/sessions")
    assert r.status_code == 200
    assert r.json() == [created]


async def test_list_public_sessions_orders_most_recently_updated_first(client):
    _, slug = await _create_shared_agent(client)
    first = (await client.post(f"/api/public/agents/{slug}/sessions")).json()
    second = (await client.post(f"/api/public/agents/{slug}/sessions")).json()

    r = await client.get(f"/api/public/agents/{slug}/sessions")
    ids = [s["id"] for s in r.json()]
    assert ids == [second["id"], first["id"]]


async def test_different_visitors_do_not_see_each_others_sessions(client):
    """
    Given visitor A has created a session
    When visitor B (a fresh cookie jar) lists sessions for the same agent
    Then visitor B must see an empty list, not visitor A's session
    """
    _, slug = await _create_shared_agent(client)
    await client.post(f"/api/public/agents/{slug}/sessions")  # visitor A

    client.cookies.clear()  # now "visitor B"
    r = await client.get(f"/api/public/agents/{slug}/sessions")
    assert r.status_code == 200
    assert r.json() == []


async def test_returning_visitor_sees_their_own_past_sessions(client):
    _, slug = await _create_shared_agent(client)
    created = (await client.post(f"/api/public/agents/{slug}/sessions")).json()

    # Same client/cookie jar = same visitor, calling again later.
    r = await client.get(f"/api/public/agents/{slug}/sessions")
    assert r.json() == [created]


async def test_admin_session_list_excludes_visitor_sessions(client):
    """The admin app's own session list must never show visitor sessions,
    and vice versa — the two are entirely separate lists."""
    aid, slug = await _create_shared_agent(client)
    await client.post(f"/api/public/agents/{slug}/sessions")

    r = await client.get(f"/api/agents/{aid}/sessions")
    assert r.status_code == 200
    assert r.json() == []


# ── Visitor session messages ──────────────────────────────────────────────────


async def test_new_public_session_has_no_messages(client):
    _, slug = await _create_shared_agent(client)
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    r = await client.get(f"/api/public/agents/{slug}/sessions/{sid}/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_public_messages_unknown_slug_returns_404(client):
    r = await client.get(
        "/api/public/agents/does-not-exist/sessions/"
        "00000000-0000-0000-0000-000000000000/messages"
    )
    assert r.status_code == 404


async def test_public_messages_unknown_session_returns_404(client):
    _, slug = await _create_shared_agent(client)
    r = await client.get(
        f"/api/public/agents/{slug}/sessions/00000000-0000-0000-0000-000000000000/messages"
    )
    assert r.status_code == 404


async def test_public_messages_malformed_session_uuid_returns_422(client):
    _, slug = await _create_shared_agent(client)
    r = await client.get(f"/api/public/agents/{slug}/sessions/not-a-uuid/messages")
    assert r.status_code == 422


async def test_visitor_cannot_read_another_visitors_session_messages(client):
    """
    Given visitor A created a session
    When visitor B requests that exact session's messages
    Then it must 404 (not 403 — a guess can't distinguish "wrong visitor"
    from "session doesn't exist")
    """
    _, slug = await _create_shared_agent(client)
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    client.cookies.clear()  # visitor B
    r = await client.get(f"/api/public/agents/{slug}/sessions/{sid}/messages")
    assert r.status_code == 404


async def test_visitor_session_from_one_agent_is_unreachable_via_another_agents_slug(
    client,
):
    """A session id that's real, but belongs to a different agent's share
    link, must 404 under the wrong slug."""
    _, slug_a = await _create_shared_agent(client, name="Agent A")
    sid_a = (await client.post(f"/api/public/agents/{slug_a}/sessions")).json()["id"]

    _, slug_b = await _create_shared_agent(client, name="Agent B")
    r = await client.get(f"/api/public/agents/{slug_b}/sessions/{sid_a}/messages")
    assert r.status_code == 404


async def test_admin_chat_route_rejects_a_visitor_owned_session(client):
    """A visitor-scoped session must never be usable on the authenticated
    admin chat route, even for the same agent."""
    aid, slug = await _create_shared_agent(client)
    visitor_sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()[
        "id"
    ]

    r = await client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "Hello?", "session_id": visitor_sid},
    )
    assert r.status_code == 404
