from unittest.mock import patch


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_project_minimal(client):
    r = await client.post("/api/projects", json={"name": "Alpha"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Alpha"
    assert body["description"] is None
    assert "id" in body
    assert "created_at" in body


async def test_create_project_with_description(client):
    r = await client.post(
        "/api/projects", json={"name": "Legal", "description": "Legal docs"}
    )
    assert r.status_code == 201
    assert r.json()["description"] == "Legal docs"


async def test_create_project_name_required(client):
    r = await client.post("/api/projects", json={})
    assert r.status_code == 422


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_projects_empty(client):
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_projects_returns_all(client):
    await client.post("/api/projects", json={"name": "Alpha"})
    await client.post("/api/projects", json={"name": "Beta"})
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── Get ───────────────────────────────────────────────────────────────────────


async def test_get_project(client):
    pid = (await client.post("/api/projects", json={"name": "Gamma"})).json()["id"]
    r = await client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Gamma"


async def test_get_project_not_found(client):
    r = await client.get("/api/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────────────


async def test_delete_project(client):
    pid = (await client.post("/api/projects", json={"name": "To Delete"})).json()["id"]
    with patch("services.project_service.chroma_delete_project"):
        r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404


async def test_delete_project_not_found(client):
    with patch("services.project_service.chroma_delete_project"):
        r = await client.delete("/api/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_delete_project_cascades_agents(client):
    """Deleting a project must also delete all its agents (cascade)."""
    pid = (await client.post("/api/projects", json={"name": "Parent"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Child"})
    ).json()["id"]
    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{pid}")
    # The agent should no longer be reachable
    assert (await client.get(f"/api/agents/{aid}")).status_code == 404


async def test_delete_project_removes_it_from_list(client):
    pid = (await client.post("/api/projects", json={"name": "Gone"})).json()["id"]
    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{pid}")
    projects = (await client.get("/api/projects")).json()
    assert all(p["id"] != pid for p in projects)
