"""
BDD-style, black-box API contract tests: pure HTTP in, JSON out, no
db_session/service pokes. Where the other test_bdd_*.py files exercise each
resource's documented behavior, this file exercises the *undocumented*
edges of the contract every route shares — unsupported HTTP methods,
malformed bodies, wrong content types, and unknown routes — proving each
endpoint only responds to exactly what it's supposed to.
"""

import pytest

pytestmark = pytest.mark.integration

_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


async def _create_project_and_agent(client) -> tuple[str, str]:
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Bot"})
    ).json()["id"]
    return pid, aid


# ── Unsupported methods: /api/projects ───────────────────────────────────────


async def test_put_on_projects_collection_returns_405(client):
    r = await client.put("/api/projects")
    assert r.status_code == 405


async def test_delete_on_projects_collection_returns_405(client):
    r = await client.delete("/api/projects")
    assert r.status_code == 405


async def test_patch_on_projects_collection_returns_405(client):
    r = await client.patch("/api/projects")
    assert r.status_code == 405


async def test_post_on_single_project_returns_405(client):
    r = await client.post(f"/api/projects/{_ZERO_UUID}")
    assert r.status_code == 405


async def test_put_on_single_project_returns_405(client):
    """There is no PUT /api/projects/{id} endpoint at all — projects can't
    be updated via the API, only created and deleted."""
    r = await client.put(f"/api/projects/{_ZERO_UUID}", json={"name": "X"})
    assert r.status_code == 405


# ── Unsupported methods: /api/projects/{id}/agents ───────────────────────────


async def test_put_on_project_agents_collection_returns_405(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.put(f"/api/projects/{pid}/agents")
    assert r.status_code == 405


async def test_delete_on_project_agents_collection_returns_405(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.delete(f"/api/projects/{pid}/agents")
    assert r.status_code == 405


# ── Unsupported methods: /api/agents/{id} ────────────────────────────────────


async def test_post_on_single_agent_returns_405(client):
    r = await client.post(f"/api/agents/{_ZERO_UUID}")
    assert r.status_code == 405


async def test_patch_on_single_agent_returns_405(client):
    """The route only supports PUT for full-ish updates, not PATCH."""
    r = await client.patch(f"/api/agents/{_ZERO_UUID}", json={"name": "X"})
    assert r.status_code == 405


# ── Unsupported methods: /api/agents/{id}/chat ───────────────────────────────


async def test_get_on_agent_chat_returns_405(client):
    r = await client.get(f"/api/agents/{_ZERO_UUID}/chat")
    assert r.status_code == 405


async def test_put_on_agent_chat_returns_405(client):
    r = await client.put(f"/api/agents/{_ZERO_UUID}/chat")
    assert r.status_code == 405


async def test_delete_on_agent_chat_returns_405(client):
    r = await client.delete(f"/api/agents/{_ZERO_UUID}/chat")
    assert r.status_code == 405


# ── Unsupported methods: /api/agents/{id}/messages ───────────────────────────


async def test_post_on_agent_messages_returns_405(client):
    r = await client.post(f"/api/agents/{_ZERO_UUID}/messages")
    assert r.status_code == 405


async def test_delete_on_agent_messages_returns_405(client):
    r = await client.delete(f"/api/agents/{_ZERO_UUID}/messages")
    assert r.status_code == 405


# ── Unsupported methods: /api/agents/{id}/share ──────────────────────────────


async def test_get_on_agent_share_returns_405(client):
    r = await client.get(f"/api/agents/{_ZERO_UUID}/share")
    assert r.status_code == 405


async def test_put_on_agent_share_returns_405(client):
    r = await client.put(f"/api/agents/{_ZERO_UUID}/share")
    assert r.status_code == 405


# ── Unsupported methods: /api/agents/{id}/sessions ───────────────────────────


async def test_put_on_agent_sessions_returns_405(client):
    r = await client.put(f"/api/agents/{_ZERO_UUID}/sessions")
    assert r.status_code == 405


async def test_delete_on_agent_sessions_returns_405(client):
    r = await client.delete(f"/api/agents/{_ZERO_UUID}/sessions")
    assert r.status_code == 405


# ── Unsupported methods: /api/sessions/{id}/messages ─────────────────────────


async def test_post_on_session_messages_returns_405(client):
    r = await client.post(f"/api/sessions/{_ZERO_UUID}/messages")
    assert r.status_code == 405


async def test_put_on_session_messages_returns_405(client):
    r = await client.put(f"/api/sessions/{_ZERO_UUID}/messages")
    assert r.status_code == 405


async def test_delete_on_session_messages_returns_405(client):
    r = await client.delete(f"/api/sessions/{_ZERO_UUID}/messages")
    assert r.status_code == 405


# ── Unsupported methods: /api/projects/{id}/files ────────────────────────────


async def test_post_on_files_listing_path_returns_405(client):
    """Upload lives at /files/upload, not /files — POSTing to the bare
    listing path must 405, not silently accept an upload."""
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/files")
    assert r.status_code == 405


async def test_put_on_files_listing_returns_405(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.put(f"/api/projects/{pid}/files")
    assert r.status_code == 405


async def test_delete_on_files_listing_returns_405(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.delete(f"/api/projects/{pid}/files")
    assert r.status_code == 405


async def test_get_on_files_upload_path_returns_405(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.get(f"/api/projects/{pid}/files/upload")
    assert r.status_code == 405


async def test_get_on_single_file_returns_405(client):
    """There is no GET /api/projects/{id}/files/{file_id} — only DELETE."""
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.get(f"/api/projects/{pid}/files/{_ZERO_UUID}")
    assert r.status_code == 405


async def test_post_on_single_file_returns_405(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/files/{_ZERO_UUID}")
    assert r.status_code == 405


# ── Unsupported methods: /api/public/agents/{slug} ───────────────────────────


async def test_post_on_public_agent_view_returns_405(client):
    r = await client.post("/api/public/agents/some-slug")
    assert r.status_code == 405


async def test_delete_on_public_agent_view_returns_405(client):
    r = await client.delete("/api/public/agents/some-slug")
    assert r.status_code == 405


# ── Unsupported methods: public sessions / messages / chat ───────────────────


async def test_put_on_public_sessions_returns_405(client):
    r = await client.put("/api/public/agents/some-slug/sessions")
    assert r.status_code == 405


async def test_post_on_public_session_messages_returns_405(client):
    r = await client.post(
        f"/api/public/agents/some-slug/sessions/{_ZERO_UUID}/messages"
    )
    assert r.status_code == 405


async def test_get_on_public_chat_returns_405(client):
    r = await client.get("/api/public/agents/some-slug/chat")
    assert r.status_code == 405


async def test_delete_on_public_chat_returns_405(client):
    r = await client.delete("/api/public/agents/some-slug/chat")
    assert r.status_code == 405


# ── Unsupported methods: /api/health ──────────────────────────────────────────


async def test_post_on_health_returns_405(client):
    r = await client.post("/api/health")
    assert r.status_code == 405


async def test_delete_on_health_returns_405(client):
    r = await client.delete("/api/health")
    assert r.status_code == 405


# ── Malformed bodies ──────────────────────────────────────────────────────────


async def test_create_project_with_syntactically_invalid_json_returns_422(client):
    r = await client.post(
        "/api/projects",
        content=b"{not valid json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


async def test_create_agent_with_syntactically_invalid_json_returns_422(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    r = await client.post(
        f"/api/projects/{pid}/agents",
        content=b"[1, 2, 3",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


async def test_create_project_with_json_array_instead_of_object_returns_422(client):
    r = await client.post("/api/projects", content=b"[1, 2, 3]")
    assert r.status_code == 422


async def test_update_agent_with_syntactically_invalid_json_returns_422(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.put(
        f"/api/agents/{aid}",
        content=b"{bad",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


async def test_create_project_with_wrong_content_type_returns_422(client):
    """A JSON-shaped body sent as text/plain isn't parsed as JSON at all."""
    r = await client.post(
        "/api/projects",
        content=b'{"name": "A"}',
        headers={"content-type": "text/plain"},
    )
    assert r.status_code == 422


async def test_generate_share_link_with_syntactically_invalid_json_returns_422(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.post(
        f"/api/agents/{aid}/share",
        content=b"{oops",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


# ── Unknown routes ────────────────────────────────────────────────────────────


async def test_unknown_top_level_route_returns_404(client):
    r = await client.get("/api/this-route-does-not-exist")
    assert r.status_code == 404


async def test_unknown_nested_route_returns_404(client):
    _, aid = await _create_project_and_agent(client)
    r = await client.get(f"/api/agents/{aid}/does-not-exist")
    assert r.status_code == 404


async def test_root_path_is_not_an_api_route(client):
    r = await client.get("/api")
    assert r.status_code in (404, 405)


# ── Trailing slash behavior ───────────────────────────────────────────────────


async def test_projects_collection_with_trailing_slash_redirects(client):
    """FastAPI/Starlette's default redirect_slashes behavior — documented
    here so a future change to that default doesn't go unnoticed."""
    r = await client.get("/api/projects/", follow_redirects=False)
    assert r.status_code == 307


async def test_following_the_trailing_slash_redirect_reaches_the_real_route(client):
    r = await client.get("/api/projects/", follow_redirects=True)
    assert r.status_code == 200


# ── Response content type ────────────────────────────────────────────────────


async def test_successful_responses_are_application_json(client):
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


async def test_error_responses_are_also_application_json(client):
    r = await client.get(f"/api/projects/{_ZERO_UUID}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "detail" in r.json()
