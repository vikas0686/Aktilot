"""
BDD-style, black-box API tests for /api/agents/{id}/share and the public
/api/public/agents/{slug} view — pure HTTP in, JSON out, no db_session/
service pokes. See test_bdd_projects.py for the shared rationale.
"""

import pytest

from config import settings

pytestmark = pytest.mark.integration


async def _create_project_and_agent(client, **agent_overrides) -> tuple[str, str]:
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    payload = {"name": "Bot"}
    payload.update(agent_overrides)
    aid = (await client.post(f"/api/projects/{pid}/agents", json=payload)).json()["id"]
    return pid, aid


# ── Generate: success ─────────────────────────────────────────────────────────


async def test_generate_share_link_with_default_cap_succeeds(client):
    """
    Given an agent exists
    When a share link is generated without an explicit cap
    Then it gets a slug, a matching share_path, and the configured default cap
    """
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["share_slug"]
    assert body["share_path"] == f"/share/{body['share_slug']}"
    assert body["daily_message_cap"] == settings.share_default_daily_message_cap


async def test_generate_share_link_with_custom_cap_succeeds(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 5})
    assert r.status_code == 200
    assert r.json()["daily_message_cap"] == 5


async def test_generate_share_link_cap_of_one_succeeds(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 1})
    assert r.status_code == 200
    assert r.json()["daily_message_cap"] == 1


async def test_generate_share_link_empty_body_uses_default_cap(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", content=b"{}")
    assert r.status_code == 200
    assert r.json()["daily_message_cap"] == settings.share_default_daily_message_cap


async def test_generate_share_link_then_get_agent_reflects_it(client):
    _, aid = await _create_project_and_agent(client)
    share = (
        await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 25})
    ).json()

    got = (await client.get(f"/api/agents/{aid}")).json()
    assert got["share_slug"] == share["share_slug"]
    assert got["share_daily_message_cap"] == 25


async def test_two_agents_get_different_slugs(client):
    _, aid1 = await _create_project_and_agent(client)
    _, aid2 = await _create_project_and_agent(client)
    slug1 = (await client.post(f"/api/agents/{aid1}/share", json={})).json()[
        "share_slug"
    ]
    slug2 = (await client.post(f"/api/agents/{aid2}/share", json={})).json()[
        "share_slug"
    ]
    assert slug1 != slug2


# ── Generate: regeneration ────────────────────────────────────────────────────


async def test_regenerating_share_link_changes_the_slug(client):
    _, aid = await _create_project_and_agent(client)
    old = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]
    new = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]
    assert new != old


async def test_regenerating_share_link_invalidates_the_old_slug(client):
    _, aid = await _create_project_and_agent(client)
    old_slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()[
        "share_slug"
    ]
    await client.post(f"/api/agents/{aid}/share", json={})

    r = await client.get(f"/api/public/agents/{old_slug}")
    assert r.status_code == 404


async def test_regenerating_share_link_then_get_agent_shows_new_slug(client):
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={})
    new = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    got = (await client.get(f"/api/agents/{aid}")).json()
    assert got["share_slug"] == new


async def test_regenerating_share_link_can_change_the_cap(client):
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 5})
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 500})
    assert r.json()["daily_message_cap"] == 500

    got = (await client.get(f"/api/agents/{aid}")).json()
    assert got["share_daily_message_cap"] == 500


# ── Generate: validation / failures ───────────────────────────────────────────


async def test_generate_share_link_agent_not_found_returns_404(client):
    r = await client.post(
        "/api/agents/00000000-0000-0000-0000-000000000000/share", json={}
    )
    assert r.status_code == 404


async def test_generate_share_link_malformed_agent_uuid_returns_422(client):
    r = await client.post("/api/agents/not-a-uuid/share", json={})
    assert r.status_code == 422


async def test_generate_share_link_cap_zero_returns_422(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 0})
    assert r.status_code == 422


async def test_generate_share_link_negative_cap_returns_422(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": -5})
    assert r.status_code == 422


async def test_generate_share_link_non_integer_cap_returns_422(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(
        f"/api/agents/{aid}/share", json={"daily_message_cap": "many"}
    )
    assert r.status_code == 422


async def test_generate_share_link_null_cap_uses_default(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": None})
    assert r.status_code == 200
    assert r.json()["daily_message_cap"] == settings.share_default_daily_message_cap


# ── Revoke ────────────────────────────────────────────────────────────────────


async def test_revoke_share_link_succeeds(client):
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={})
    r = await client.delete(f"/api/agents/{aid}/share")
    assert r.status_code == 204


async def test_revoke_share_link_then_get_agent_shows_null_slug(client):
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={})
    await client.delete(f"/api/agents/{aid}/share")

    got = (await client.get(f"/api/agents/{aid}")).json()
    assert got["share_slug"] is None


async def test_revoke_share_link_then_public_view_404s(client):
    _, aid = await _create_project_and_agent(client)
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]
    await client.delete(f"/api/agents/{aid}/share")

    r = await client.get(f"/api/public/agents/{slug}")
    assert r.status_code == 404


async def test_revoke_share_link_agent_not_found_returns_404(client):
    r = await client.delete("/api/agents/00000000-0000-0000-0000-000000000000/share")
    assert r.status_code == 404


async def test_revoke_share_link_malformed_agent_uuid_returns_422(client):
    r = await client.delete("/api/agents/not-a-uuid/share")
    assert r.status_code == 422


async def test_revoke_share_link_on_never_shared_agent_is_a_noop_success(client):
    """revoke_share_link only checks the agent exists, not that it was ever
    shared — revoking an agent that was never shared still succeeds."""
    _, aid = await _create_project_and_agent(client)
    r = await client.delete(f"/api/agents/{aid}/share")
    assert r.status_code == 204


async def test_revoke_share_link_twice_both_succeed(client):
    """Unlike project/agent delete (idempotent-but-second-call-404s),
    revoke is a pure state-setter and succeeds every time the agent exists."""
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={})
    first = await client.delete(f"/api/agents/{aid}/share")
    second = await client.delete(f"/api/agents/{aid}/share")
    assert first.status_code == 204
    assert second.status_code == 204


async def test_revoke_share_link_preserves_the_daily_cap_value(client):
    """revoke only clears share_slug — share_daily_message_cap is left as-is
    (it's inert once share_slug is None, and generate always overwrites it
    fresh on the next share anyway)."""
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": 25})
    await client.delete(f"/api/agents/{aid}/share")

    got = (await client.get(f"/api/agents/{aid}")).json()
    assert got["share_daily_message_cap"] == 25


async def test_revoke_share_link_does_not_delete_the_agent(client):
    _, aid = await _create_project_and_agent(client)
    await client.post(f"/api/agents/{aid}/share", json={})
    await client.delete(f"/api/agents/{aid}/share")

    r = await client.get(f"/api/agents/{aid}")
    assert r.status_code == 200


# ── Public view ───────────────────────────────────────────────────────────────


async def test_public_view_of_unknown_slug_returns_404(client):
    r = await client.get("/api/public/agents/this-slug-does-not-exist")
    assert r.status_code == 404


async def test_public_view_exposes_only_name_and_description(client):
    _, aid = await _create_project_and_agent(
        client, name="Helper", description="A helpful bot"
    )
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    r = await client.get(f"/api/public/agents/{slug}")
    assert r.status_code == 200
    assert r.json() == {"name": "Helper", "description": "A helpful bot"}


async def test_public_view_does_not_expose_project_or_config_fields(client):
    _, aid = await _create_project_and_agent(
        client, name="Helper", system_prompt="secret prompt", top_k=7
    )
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    r = await client.get(f"/api/public/agents/{slug}")
    body = r.json()
    assert "system_prompt" not in body
    assert "top_k" not in body
    assert "project_id" not in body
    assert "id" not in body


async def test_public_view_with_null_description(client):
    _, aid = await _create_project_and_agent(client, name="Helper")
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    r = await client.get(f"/api/public/agents/{slug}")
    assert r.json()["description"] is None
