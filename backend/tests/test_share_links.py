"""Tests for agent share links and anonymous visitor chat isolation.

Covers: generating/revoking share links, the public agent view leaking
nothing about the project, visitor session isolation between different
"browsers" (cookie jars), the admin app never seeing visitor conversations,
per-visitor/per-agent rate limits, and the retention purge.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from config import settings
from main import app
from services import message_service, session_service

_FAKE_RESULT = {
    "answer": "The answer is 42.",
    "keywords": [],
    "chunks": [],
    "steps": [],
}


def _mock_temporal(result: dict = _FAKE_RESULT):
    mock_tc = MagicMock()
    mock_tc.execute_workflow = AsyncMock(return_value=result)
    return (
        patch(
            "api.routes.agent_chat.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_tc,
        ),
        mock_tc,
    )


async def _make_agent(client, name="A", description=None) -> tuple[str, str]:
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    body = {"name": name}
    if description is not None:
        body["description"] = description
    aid = (await client.post(f"/api/projects/{pid}/agents", json=body)).json()["id"]
    return pid, aid


async def _share(client, agent_id: str, daily_cap: int | None = None) -> str:
    payload = {"daily_message_cap": daily_cap} if daily_cap is not None else {}
    r = await client.post(f"/api/agents/{agent_id}/share", json=payload)
    assert r.status_code == 200
    return r.json()["share_slug"]


def _second_client() -> AsyncClient:
    """A fresh cookie jar against the same app/db — simulates a different browser."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Share link lifecycle ───────────────────────────────────────────────────────


async def test_generate_share_link_returns_slug_and_path(client):
    _, aid = await _make_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["share_slug"]
    assert body["share_path"] == f"/share/{body['share_slug']}"
    assert body["daily_message_cap"] == settings.share_default_daily_message_cap


async def test_generate_share_link_honors_custom_daily_cap(client):
    _, aid = await _make_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 5})
    assert r.json()["daily_message_cap"] == 5


async def test_regenerate_share_link_invalidates_old_slug(client):
    _, aid = await _make_agent(client)
    old_slug = await _share(client, aid)
    new_slug = await _share(client, aid)
    assert old_slug != new_slug

    assert (await client.get(f"/api/public/agents/{old_slug}")).status_code == 404
    assert (await client.get(f"/api/public/agents/{new_slug}")).status_code == 200


async def test_revoke_share_link_disables_public_access(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    assert (await client.get(f"/api/public/agents/{slug}")).status_code == 200

    r = await client.delete(f"/api/agents/{aid}/share")
    assert r.status_code == 204
    assert (await client.get(f"/api/public/agents/{slug}")).status_code == 404


async def test_unknown_slug_returns_404(client):
    r = await client.get("/api/public/agents/does-not-exist")
    assert r.status_code == 404


# ── Public agent view leaks nothing about the project ─────────────────────────


async def test_public_agent_view_excludes_project_and_internal_fields(client):
    _, aid = await _make_agent(
        client, name="Support Bot", description="Helps customers"
    )
    slug = await _share(client, aid)

    r = await client.get(f"/api/public/agents/{slug}")
    assert r.status_code == 200
    body = r.json()
    assert body == {"name": "Support Bot", "description": "Helps customers"}
    assert "project_id" not in body
    assert "system_prompt" not in body
    assert "top_k" not in body
    assert "id" not in body


# ── Visitor identity + isolation ───────────────────────────────────────────────


async def test_first_public_request_sets_visitor_cookie(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    r = await client.get(f"/api/public/agents/{slug}")
    assert settings.share_visitor_cookie_name in r.cookies


async def test_visitor_can_create_multiple_sessions_with_same_agent(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)

    sid1 = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]
    sid2 = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]
    assert sid1 != sid2

    ids = {
        s["id"]
        for s in (await client.get(f"/api/public/agents/{slug}/sessions")).json()
    }
    assert ids == {sid1, sid2}


async def test_different_browsers_cannot_see_each_others_sessions(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)

    sid_a = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    async with _second_client() as client_b:
        r = await client_b.post(f"/api/public/agents/{slug}/sessions")
        sid_b = r.json()["id"]
        assert sid_b != sid_a

        listed = {
            s["id"]
            for s in (await client_b.get(f"/api/public/agents/{slug}/sessions")).json()
        }
        assert listed == {sid_b}
        assert sid_a not in listed

        r = await client_b.get(f"/api/public/agents/{slug}/sessions/{sid_a}/messages")
        assert r.status_code == 404

        patcher, _ = _mock_temporal()
        with patcher:
            r = await client_b.post(
                f"/api/public/agents/{slug}/chat",
                json={"question": "hi", "session_id": sid_a},
            )
        assert r.status_code == 404


async def test_returning_visitor_sees_own_past_sessions(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    # Same client instance == same cookie jar == "returning" in the same browser.
    ids = {
        s["id"]
        for s in (await client.get(f"/api/public/agents/{slug}/sessions")).json()
    }
    assert sid in ids


# ── Admin app never sees visitor conversations ────────────────────────────────


async def test_admin_session_list_excludes_visitor_sessions(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    await client.post(f"/api/public/agents/{slug}/sessions")

    admin_sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    ids = [s["id"] for s in (await client.get(f"/api/agents/{aid}/sessions")).json()]
    assert ids == [admin_sid]


async def test_admin_message_list_excludes_visitor_messages(client, db_session):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    visitor_sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()[
        "id"
    ]
    admin_sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    await message_service.create(
        db_session,
        uuid.UUID(aid),
        "user",
        "visitor question",
        session_id=uuid.UUID(visitor_sid),
    )
    await message_service.create(
        db_session,
        uuid.UUID(aid),
        "user",
        "admin question",
        session_id=uuid.UUID(admin_sid),
    )

    r = await client.get(f"/api/agents/{aid}/messages")
    contents = [m["content"] for m in r.json()]
    assert contents == ["admin question"]


# ── Rate limiting ──────────────────────────────────────────────────────────────


async def test_public_chat_hourly_visitor_limit_returns_429(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "share_visitor_hourly_message_cap", 2)
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    for _ in range(2):
        await message_service.create(
            db_session, uuid.UUID(aid), "user", "hi", session_id=uuid.UUID(sid)
        )

    patcher, _ = _mock_temporal()
    with patcher:
        r = await client.post(
            f"/api/public/agents/{slug}/chat",
            json={"question": "one more", "session_id": sid},
        )
    assert r.status_code == 429


async def test_public_chat_daily_agent_cap_returns_429(client, db_session):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid, daily_cap=2)
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    for _ in range(2):
        await message_service.create(
            db_session, uuid.UUID(aid), "user", "hi", session_id=uuid.UUID(sid)
        )

    patcher, _ = _mock_temporal()
    with patcher:
        r = await client.post(
            f"/api/public/agents/{slug}/chat",
            json={"question": "one more", "session_id": sid},
        )
    assert r.status_code == 429


async def test_regenerating_link_resets_daily_cap_window(client, db_session):
    """Regression test: lowering the daily cap on regenerate must not
    retroactively count messages sent earlier under a higher/older cap."""
    _, aid = await _make_agent(client)
    old_slug = await _share(client, aid)  # generous default cap
    old_sid = (await client.post(f"/api/public/agents/{old_slug}/sessions")).json()[
        "id"
    ]

    # 3 messages sent earlier today, before the cap was ever lowered.
    for _ in range(3):
        await message_service.create(
            db_session, uuid.UUID(aid), "user", "hi", session_id=uuid.UUID(old_sid)
        )

    new_slug = await _share(client, aid, daily_cap=2)
    new_sid = (await client.post(f"/api/public/agents/{new_slug}/sessions")).json()[
        "id"
    ]

    patcher, _ = _mock_temporal()
    with patcher:
        r = await client.post(
            f"/api/public/agents/{new_slug}/chat",
            json={
                "question": "first message after regenerating",
                "session_id": new_sid,
            },
        )
    assert r.status_code == 200


async def test_public_chat_succeeds_under_limits(client):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    sid = (await client.post(f"/api/public/agents/{slug}/sessions")).json()["id"]

    patcher, _ = _mock_temporal()
    with patcher:
        r = await client.post(
            f"/api/public/agents/{slug}/chat",
            json={"question": "hello", "session_id": sid},
        )
    assert r.status_code == 200
    assert r.json()["answer"] == "The answer is 42."


# ── Retention purge ────────────────────────────────────────────────────────────


async def test_purge_deletes_only_expired_visitor_sessions(client, db_session):
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)

    stale_visitor_sid = (
        await client.post(f"/api/public/agents/{slug}/sessions")
    ).json()["id"]
    fresh_visitor_sid = (
        await client.post(f"/api/public/agents/{slug}/sessions")
    ).json()["id"]
    admin_sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=8)
    stale_session = await session_service.get(db_session, uuid.UUID(stale_visitor_sid))
    stale_session.updated_at = stale_cutoff
    old_admin_session = await session_service.get(db_session, uuid.UUID(admin_sid))
    old_admin_session.updated_at = stale_cutoff
    await db_session.commit()

    deleted = await session_service.purge_expired_visitor_sessions(
        db_session, retention_days=7
    )
    assert deleted == 1

    remaining_ids = {
        s["id"]
        for s in (await client.get(f"/api/public/agents/{slug}/sessions")).json()
    }
    assert remaining_ids == {fresh_visitor_sid}

    # Admin session is untouched even though it was equally stale — retention
    # only ever applies to anonymous visitor sessions.
    assert (await client.get(f"/api/agents/{aid}/sessions")).status_code == 200
    admin_ids = [
        s["id"] for s in (await client.get(f"/api/agents/{aid}/sessions")).json()
    ]
    assert admin_sid in admin_ids
