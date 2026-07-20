"""
BDD-style, black-box API tests for /api/projects/{id}/agents and
/api/agents/{id} — pure HTTP in, JSON out, no db_session/service pokes.
See test_bdd_projects.py for the shared rationale.
"""

import pytest

pytestmark = pytest.mark.integration


async def _create_project(client, name: str = "P") -> str:
    return (await client.post("/api/projects", json={"name": name})).json()["id"]


async def _create_agent(client, project_id: str, **overrides) -> dict:
    payload = {"name": "Agent"}
    payload.update(overrides)
    return (
        await client.post(f"/api/projects/{project_id}/agents", json=payload)
    ).json()


# ── Create: success ───────────────────────────────────────────────────────────


async def test_create_agent_with_minimal_fields_succeeds(client):
    """
    Given a project exists
    When an agent is created with just a name
    Then it gets the documented defaults for the other fields
    """
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Bot"
    assert body["project_id"] == pid
    assert body["top_k"] == 2
    assert body["system_prompt"] == ""
    assert body["description"] is None
    assert body["share_slug"] is None
    assert body["share_daily_message_cap"] is None


async def test_create_agent_with_all_fields_succeeds(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents",
        json={
            "name": "Analyst",
            "description": "Data bot",
            "system_prompt": "Be concise.",
            "top_k": 5,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["description"] == "Data bot"
    assert body["system_prompt"] == "Be concise."
    assert body["top_k"] == 5


async def test_create_agent_top_k_one_succeeds(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": 1}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == 1


async def test_create_agent_top_k_ten_succeeds(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": 10}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == 10


async def test_create_two_agents_under_same_project_get_distinct_ids(client):
    pid = await _create_project(client)
    a = await _create_agent(client, pid, name="Same")
    b = await _create_agent(client, pid, name="Same")
    assert a["id"] != b["id"]


async def test_create_agent_unicode_fields_round_trip_exactly(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents",
        json={"name": "日本語ボット\U0001f916", "description": "説明文"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "日本語ボット\U0001f916"
    assert body["description"] == "説明文"


# ── Create: validation / edge cases ──────────────────────────────────────────


async def test_create_agent_project_not_found_returns_404(client):
    r = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/agents",
        json={"name": "Ghost"},
    )
    assert r.status_code == 404


async def test_create_agent_project_malformed_uuid_returns_422(client):
    r = await client.post("/api/projects/not-a-uuid/agents", json={"name": "X"})
    assert r.status_code == 422


async def test_create_agent_missing_name_returns_422(client):
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={})
    assert r.status_code == 422


async def test_create_agent_non_integer_top_k_returns_422(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": "five"}
    )
    assert r.status_code == 422


async def test_create_agent_empty_name_is_currently_accepted(client):
    """Known gap: AgentCreate.name has no min_length constraint."""
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={"name": ""})
    assert r.status_code == 201


async def test_create_agent_top_k_zero_is_currently_accepted(client):
    """Known gap: AgentCreate.top_k has no bounds check server-side."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": 0}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == 0


async def test_create_agent_top_k_negative_is_currently_accepted(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": -1}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == -1


async def test_create_agent_top_k_very_large_is_currently_accepted(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": 999999}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == 999999


# ── Get ───────────────────────────────────────────────────────────────────────


async def test_get_existing_agent_returns_it(client):
    pid = await _create_project(client)
    created = await _create_agent(client, pid, name="Finder")
    r = await client.get(f"/api/agents/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


async def test_get_agent_valid_uuid_no_match_returns_404(client):
    r = await client.get("/api/agents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_get_agent_malformed_uuid_returns_422(client):
    r = await client.get("/api/agents/not-a-uuid")
    assert r.status_code == 422


async def test_get_agent_after_delete_returns_404(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    await client.delete(f"/api/agents/{aid}")
    r = await client.get(f"/api/agents/{aid}")
    assert r.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_agents_for_project_with_none_returns_empty(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/agents")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_agents_project_not_found_returns_404(client):
    r = await client.get("/api/projects/00000000-0000-0000-0000-000000000000/agents")
    assert r.status_code == 404


async def test_list_agents_returns_only_this_projects_agents(client):
    pid1 = await _create_project(client, "P1")
    pid2 = await _create_project(client, "P2")
    a = await _create_agent(client, pid1, name="A")
    b = await _create_agent(client, pid1, name="B")
    await _create_agent(client, pid2, name="C")

    r = await client.get(f"/api/projects/{pid1}/agents")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert {x["id"] for x in body} == {a["id"], b["id"]}


async def test_list_agents_orders_oldest_created_first(client):
    """Unlike projects (newest first), agents list oldest-created first."""
    pid = await _create_project(client)
    first = await _create_agent(client, pid, name="First")
    second = await _create_agent(client, pid, name="Second")
    third = await _create_agent(client, pid, name="Third")

    r = await client.get(f"/api/projects/{pid}/agents")
    ids = [a["id"] for a in r.json()]
    assert ids == [first["id"], second["id"], third["id"]]


async def test_list_agents_after_delete_excludes_it(client):
    pid = await _create_project(client)
    keep = await _create_agent(client, pid, name="Keep")
    remove = await _create_agent(client, pid, name="Remove")
    await client.delete(f"/api/agents/{remove['id']}")

    r = await client.get(f"/api/projects/{pid}/agents")
    ids = [a["id"] for a in r.json()]
    assert ids == [keep["id"]]


# ── Update: success ───────────────────────────────────────────────────────────


async def test_update_agent_name_only(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid, name="Old"))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


async def test_update_agent_description_only(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"description": "Updated"})
    assert r.status_code == 200
    assert r.json()["description"] == "Updated"


async def test_update_agent_system_prompt_only(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"system_prompt": "New prompt"})
    assert r.status_code == 200
    assert r.json()["system_prompt"] == "New prompt"


async def test_update_agent_top_k_only(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"top_k": 8})
    assert r.status_code == 200
    assert r.json()["top_k"] == 8


async def test_update_agent_all_fields_at_once(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(
        f"/api/agents/{aid}",
        json={
            "name": "Renamed",
            "description": "New desc",
            "system_prompt": "New prompt",
            "top_k": 4,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["description"] == "New desc"
    assert body["system_prompt"] == "New prompt"
    assert body["top_k"] == 4


async def test_update_agent_partial_update_preserves_other_fields(client):
    """Updating just one field must leave the others exactly as they were."""
    pid = await _create_project(client)
    aid = (
        await _create_agent(
            client,
            pid,
            name="Original",
            description="Original desc",
            system_prompt="Original prompt",
            top_k=4,
        )
    )["id"]

    r = await client.put(f"/api/agents/{aid}", json={"name": "Renamed"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["description"] == "Original desc"
    assert body["system_prompt"] == "Original prompt"
    assert body["top_k"] == 4


async def test_update_agent_empty_body_is_a_noop(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid, name="Original", top_k=3))["id"]

    r = await client.put(f"/api/agents/{aid}", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Original"
    assert body["top_k"] == 3


async def test_update_agent_then_a_fresh_get_reflects_the_change(client):
    """The PUT response isn't just an echo — a separate GET must agree."""
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid, name="Old"))["id"]

    await client.put(f"/api/agents/{aid}", json={"name": "New"})

    r = await client.get(f"/api/agents/{aid}")
    assert r.json()["name"] == "New"


async def test_update_agent_does_not_affect_share_fields(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    share = (await client.post(f"/api/agents/{aid}/share", json={})).json()

    await client.put(f"/api/agents/{aid}", json={"name": "Renamed"})

    got = (await client.get(f"/api/agents/{aid}")).json()
    assert got["share_slug"] == share["share_slug"]


# ── Update: validation / edge cases ───────────────────────────────────────────


async def test_update_agent_not_found_returns_404(client):
    r = await client.put(
        "/api/agents/00000000-0000-0000-0000-000000000000", json={"name": "X"}
    )
    assert r.status_code == 404


async def test_update_agent_malformed_uuid_returns_422(client):
    r = await client.put("/api/agents/not-a-uuid", json={"name": "X"})
    assert r.status_code == 422


async def test_update_agent_top_k_to_zero_is_currently_accepted(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"top_k": 0})
    assert r.status_code == 200
    assert r.json()["top_k"] == 0


async def test_update_agent_name_to_empty_string_is_currently_accepted(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"name": ""})
    assert r.status_code == 200
    assert r.json()["name"] == ""


async def test_update_agent_non_integer_top_k_returns_422(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.put(f"/api/agents/{aid}", json={"top_k": "nine"})
    assert r.status_code == 422


# ── Delete ────────────────────────────────────────────────────────────────────


async def test_delete_agent_succeeds(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.delete(f"/api/agents/{aid}")
    assert r.status_code == 204


async def test_delete_agent_not_found_returns_404(client):
    r = await client.delete("/api/agents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_delete_agent_malformed_uuid_returns_422(client):
    r = await client.delete("/api/agents/not-a-uuid")
    assert r.status_code == 422


async def test_delete_agent_twice_the_second_time_404s(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    first = await client.delete(f"/api/agents/{aid}")
    second = await client.delete(f"/api/agents/{aid}")
    assert first.status_code == 204
    assert second.status_code == 404


async def test_delete_agent_does_not_affect_sibling_agent(client):
    pid = await _create_project(client)
    keep = await _create_agent(client, pid, name="Keep")
    remove = await _create_agent(client, pid, name="Remove")
    await client.delete(f"/api/agents/{remove['id']}")

    r = await client.get(f"/api/agents/{keep['id']}")
    assert r.status_code == 200


async def test_delete_agent_does_not_affect_parent_project(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    await client.delete(f"/api/agents/{aid}")

    r = await client.get(f"/api/projects/{pid}")
    assert r.status_code == 200


async def test_delete_agent_makes_its_sessions_unreachable(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    await client.delete(f"/api/agents/{aid}")

    assert (await client.get(f"/api/agents/{aid}/sessions")).status_code == 404
    assert (await client.get(f"/api/sessions/{sid}/messages")).status_code == 404


async def test_delete_agent_invalidates_its_share_link(client):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    slug = (await client.post(f"/api/agents/{aid}/share", json={})).json()["share_slug"]

    await client.delete(f"/api/agents/{aid}")

    assert (await client.get(f"/api/public/agents/{slug}")).status_code == 404
