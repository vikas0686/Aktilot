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
