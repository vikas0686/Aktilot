"""
Tests for limit/offset pagination on the previously-unbounded list endpoints:
GET /api/projects, /api/projects/{id}/files, /api/projects/{id}/agents,
/api/agents/{id}/sessions, /api/agents/{id}/messages,
/api/sessions/{id}/messages, and /api/projects/{id}/github/connections.

For the two message endpoints, pagination is most-recent-page-first (so
offset=0 with a small limit still shows the latest messages, not the
earliest) — those tests assert ordering explicitly, not just count.
"""

import uuid

from services import message_service


async def _make_project(client, name: str = "P") -> str:
    return (await client.post("/api/projects", json={"name": name})).json()["id"]


async def _make_agent(client, project_id: str, name: str = "A") -> str:
    return (
        await client.post(f"/api/projects/{project_id}/agents", json={"name": name})
    ).json()["id"]


async def _make_session(client, agent_id: str) -> str:
    return (await client.post(f"/api/agents/{agent_id}/sessions")).json()["id"]


# ── validation ──────────────────────────────────────────────────────────────


async def test_limit_zero_is_rejected(client):
    r = await client.get("/api/projects", params={"limit": 0})
    assert r.status_code == 422


async def test_limit_above_ceiling_is_rejected(client):
    r = await client.get("/api/projects", params={"limit": 501})
    assert r.status_code == 422


async def test_negative_offset_is_rejected(client):
    r = await client.get("/api/projects", params={"offset": -1})
    assert r.status_code == 422


# ── projects ────────────────────────────────────────────────────────────────


async def test_list_projects_respects_limit(client):
    for i in range(5):
        await _make_project(client, name=f"P{i}")

    r = await client.get("/api/projects", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_list_projects_offset_pages_through_results(client):
    ids = [await _make_project(client, name=f"P{i}") for i in range(3)]

    page1 = (await client.get("/api/projects", params={"limit": 2, "offset": 0})).json()
    page2 = (await client.get("/api/projects", params={"limit": 2, "offset": 2})).json()

    # newest-first ordering: page1 has the 2 most recently created, page2 has
    # the remainder, with no overlap.
    seen_ids = {p["id"] for p in page1} | {p["id"] for p in page2}
    assert seen_ids == set(ids)
    assert len(page1) == 2
    assert len(page2) == 1


# ── files ───────────────────────────────────────────────────────────────────


async def test_list_files_respects_limit(client, db_session):
    import io
    from unittest.mock import AsyncMock, MagicMock, patch

    pid = await _make_project(client)
    mock_tc = MagicMock()
    mock_tc.start_workflow = AsyncMock()
    with patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        for i in range(3):
            await client.post(
                f"/api/projects/{pid}/files/upload",
                files={"file": (f"f{i}.txt", io.BytesIO(b"x"), "text/plain")},
            )

    r = await client.get(f"/api/projects/{pid}/files", params={"limit": 1})
    assert r.status_code == 200
    assert len(r.json()) == 1


# ── agents ──────────────────────────────────────────────────────────────────


async def test_list_agents_respects_limit(client):
    pid = await _make_project(client)
    for i in range(3):
        await _make_agent(client, pid, name=f"A{i}")

    r = await client.get(f"/api/projects/{pid}/agents", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── sessions ────────────────────────────────────────────────────────────────


async def test_list_sessions_respects_limit(client):
    pid = await _make_project(client)
    aid = await _make_agent(client, pid)
    for _ in range(3):
        await _make_session(client, aid)

    r = await client.get(f"/api/agents/{aid}/sessions", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── messages (most-recent-page-first) ────────────────────────────────────────


async def test_agent_messages_limit_returns_most_recent_not_oldest(client, db_session):
    pid = await _make_project(client)
    aid = await _make_agent(client, pid)
    sid = await _make_session(client, aid)

    for i in range(5):
        await message_service.create(
            db_session, uuid.UUID(aid), "user", f"msg-{i}", session_id=uuid.UUID(sid)
        )

    r = await client.get(f"/api/agents/{aid}/messages", params={"limit": 2})
    assert r.status_code == 200
    bodies = [m["content"] for m in r.json()]
    # must be the 2 most recent messages, still in chronological (ascending) order
    assert bodies == ["msg-3", "msg-4"]


async def test_agent_messages_offset_pages_backwards_through_history(
    client, db_session
):
    pid = await _make_project(client)
    aid = await _make_agent(client, pid)
    sid = await _make_session(client, aid)

    for i in range(5):
        await message_service.create(
            db_session, uuid.UUID(aid), "user", f"msg-{i}", session_id=uuid.UUID(sid)
        )

    r = await client.get(
        f"/api/agents/{aid}/messages", params={"limit": 2, "offset": 2}
    )
    assert r.status_code == 200
    bodies = [m["content"] for m in r.json()]
    assert bodies == ["msg-1", "msg-2"]


async def test_session_messages_limit_returns_most_recent_not_oldest(
    client, db_session
):
    pid = await _make_project(client)
    aid = await _make_agent(client, pid)
    sid = await _make_session(client, aid)

    for i in range(4):
        await message_service.create(
            db_session, uuid.UUID(aid), "user", f"msg-{i}", session_id=uuid.UUID(sid)
        )

    r = await client.get(f"/api/sessions/{sid}/messages", params={"limit": 2})
    assert r.status_code == 200
    bodies = [m["content"] for m in r.json()]
    assert bodies == ["msg-2", "msg-3"]


# ── github connections ───────────────────────────────────────────────────────


async def test_list_github_connections_respects_limit(client, db_session):
    from db.models.github_connection import GithubConnection
    from db.models.github_installation import GithubInstallation

    pid = await _make_project(client)
    installation = GithubInstallation(
        project_id=uuid.UUID(pid),
        installation_id=12345,
        account_login="acme",
        account_type="Organization",
    )
    db_session.add(installation)
    await db_session.commit()
    await db_session.refresh(installation)

    for i in range(3):
        db_session.add(
            GithubConnection(
                project_id=uuid.UUID(pid),
                installation_id=installation.id,
                repo_full_name=f"acme/repo{i}",
                default_branch="main",
                sync_status="pending",
            )
        )
    await db_session.commit()

    r = await client.get(f"/api/projects/{pid}/github/connections", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2
