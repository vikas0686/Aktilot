async def _create_project(client, name: str = "Test Project") -> str:
    r = await client.post("/api/projects", json={"name": name})
    return r.json()["id"]


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_agent_minimal(client):
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Bot"
    assert body["project_id"] == pid
    assert body["top_k"] == 2
    assert body["system_prompt"] == ""
    assert body["description"] is None


async def test_create_agent_all_fields(client):
    pid = await _create_project(client)
    payload = {
        "name": "Analyst",
        "description": "Data bot",
        "system_prompt": "Be concise.",
        "top_k": 5,
    }
    r = await client.post(f"/api/projects/{pid}/agents", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["description"] == "Data bot"
    assert body["system_prompt"] == "Be concise."
    assert body["top_k"] == 5


async def test_create_agent_project_not_found(client):
    r = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/agents",
        json={"name": "Ghost"},
    )
    assert r.status_code == 404


async def test_create_agent_name_required(client):
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={})
    assert r.status_code == 422


async def test_create_agent_empty_name_is_currently_accepted(client):
    """Known gap: AgentCreate.name has no min_length constraint (unlike, say,
    ShareLinkCreate.daily_message_cap's gt=0), so an empty string passes
    validation. Documents current behavior rather than assuming it's fine."""
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={"name": ""})
    assert r.status_code == 201
    assert r.json()["name"] == ""


async def test_create_agent_top_k_zero_is_currently_accepted(client):
    """Known gap: AgentCreate.top_k has no bounds check at all (the frontend
    clamps to 1-10 client-side, but nothing enforces that server-side), so
    0 and negative values pass straight through to the DB and into
    hybrid_rank's `ranked[:top_k]` slicing, where a negative top_k silently
    drops from the end of the list instead of erroring."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": 0}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == 0


async def test_create_agent_top_k_negative_is_currently_accepted(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": -3}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == -3


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_agents_empty(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/agents")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_agents_returns_only_project_agents(client):
    pid1 = await _create_project(client, "P1")
    pid2 = await _create_project(client, "P2")
    await client.post(f"/api/projects/{pid1}/agents", json={"name": "A"})
    await client.post(f"/api/projects/{pid1}/agents", json={"name": "B"})
    await client.post(f"/api/projects/{pid2}/agents", json={"name": "C"})

    r = await client.get(f"/api/projects/{pid1}/agents")
    assert len(r.json()) == 2
    names = {a["name"] for a in r.json()}
    assert names == {"A", "B"}


# ── Get ───────────────────────────────────────────────────────────────────────


async def test_get_agent(client):
    pid = await _create_project(client)
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Finder"})
    ).json()["id"]
    r = await client.get(f"/api/agents/{aid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Finder"


async def test_get_agent_not_found(client):
    r = await client.get("/api/agents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────


async def test_update_agent_name(client):
    pid = await _create_project(client)
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Old"})
    ).json()["id"]
    r = await client.put(f"/api/agents/{aid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


async def test_update_agent_top_k(client):
    pid = await _create_project(client)
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    r = await client.put(f"/api/agents/{aid}", json={"top_k": 8})
    assert r.status_code == 200
    assert r.json()["top_k"] == 8


async def test_update_agent_not_found(client):
    r = await client.put(
        "/api/agents/00000000-0000-0000-0000-000000000000", json={"name": "X"}
    )
    assert r.status_code == 404


async def test_update_agent_partial_update_preserves_other_fields(client):
    """Updating just one field must leave the others exactly as they were —
    AgentUpdate's fields are all optional and the service only assigns the
    ones that aren't None, but that behavior isn't locked in anywhere yet."""
    pid = await _create_project(client)
    aid = (
        await client.post(
            f"/api/projects/{pid}/agents",
            json={
                "name": "Original",
                "description": "Original desc",
                "system_prompt": "Original prompt",
                "top_k": 4,
            },
        )
    ).json()["id"]

    r = await client.put(f"/api/agents/{aid}", json={"name": "Renamed"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["description"] == "Original desc"
    assert body["system_prompt"] == "Original prompt"
    assert body["top_k"] == 4


async def test_update_agent_empty_body_is_a_noop(client):
    pid = await _create_project(client)
    aid = (
        await client.post(
            f"/api/projects/{pid}/agents",
            json={"name": "Original", "top_k": 3},
        )
    ).json()["id"]

    r = await client.put(f"/api/agents/{aid}", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Original"
    assert body["top_k"] == 3


async def test_update_agent_top_k_to_zero_is_currently_accepted(client):
    """Same gap as create — update path has no bounds check either."""
    pid = await _create_project(client)
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    r = await client.put(f"/api/agents/{aid}", json={"top_k": 0})
    assert r.status_code == 200
    assert r.json()["top_k"] == 0


# ── Delete ────────────────────────────────────────────────────────────────────


async def test_delete_agent(client):
    pid = await _create_project(client)
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Del"})
    ).json()["id"]
    r = await client.delete(f"/api/agents/{aid}")
    assert r.status_code == 204
    assert (await client.get(f"/api/agents/{aid}")).status_code == 404


async def test_delete_agent_not_found(client):
    r = await client.delete("/api/agents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
