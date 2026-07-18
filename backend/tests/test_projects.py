import io
from unittest.mock import AsyncMock, MagicMock, patch

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


async def test_create_project_empty_name_is_currently_accepted(client):
    """Known gap: ProjectCreate.name has no min_length constraint, so an
    empty string passes Pydantic validation (only a missing field doesn't).
    Documents current behavior rather than silently assuming it's intended."""
    r = await client.post("/api/projects", json={"name": ""})
    assert r.status_code == 201
    assert r.json()["name"] == ""


async def test_create_project_whitespace_only_name_is_currently_accepted(client):
    r = await client.post("/api/projects", json={"name": "   "})
    assert r.status_code == 201
    assert r.json()["name"] == "   "


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


async def test_delete_project_calls_chroma_delete_project(client):
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    with patch("services.project_service.chroma_delete_project") as mock_delete:
        await client.delete(f"/api/projects/{pid}")
    mock_delete.assert_called_once_with(pid)


async def test_delete_project_cascades_files(client, db_session):
    """Deleting a project must also delete its files (cascade), not just
    its agents — verified against the DB row directly, not just the
    now-404ing project-scoped route."""
    import uuid

    from db.models.file import File

    pid = (await client.post("/api/projects", json={"name": "Parent"})).json()["id"]
    mock_tc = MagicMock()
    mock_tc.start_workflow = AsyncMock()
    with patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        fid = (
            await client.post(
                f"/api/projects/{pid}/files/upload",
                files={"file": ("a.txt", io.BytesIO(b"content"), "text/plain")},
            )
        ).json()["id"]

    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{pid}")

    assert await db_session.get(File, uuid.UUID(fid)) is None


async def test_delete_project_cascades_sessions_and_messages(client, db_session):
    """Deleting a project must cascade through its agents to their chat
    sessions and messages too, not just the agents themselves — verified
    against the DB rows directly."""
    import uuid

    from db.models.chat_session import ChatSession
    from db.models.message import Message
    from services import message_service

    pid = (await client.post("/api/projects", json={"name": "Parent"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "Child"})
    ).json()["id"]
    sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]
    message = await message_service.create(
        db_session, uuid.UUID(aid), "user", "hello", session_id=uuid.UUID(sid)
    )

    with patch("services.project_service.chroma_delete_project"):
        r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204

    assert await db_session.get(ChatSession, uuid.UUID(sid)) is None
    assert await db_session.get(Message, message.id) is None


async def test_delete_project_removes_upload_directory_from_disk(client):
    """Deleting a project must remove its uploaded files from disk, not
    just the DB rows and the ChromaDB collection."""
    from config import project_upload_dir

    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    mock_tc = MagicMock()
    mock_tc.start_workflow = AsyncMock()
    with patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        upload_resp = await client.post(
            f"/api/projects/{pid}/files/upload",
            files={"file": ("a.txt", io.BytesIO(b"content"), "text/plain")},
        )
    assert upload_resp.status_code == 201
    fid = upload_resp.json()["id"]

    # project_upload_dir() itself mkdir()s the directory as a side effect, so
    # asserting the directory exists alone wouldn't prove the upload actually
    # wrote a file — check the specific uploaded file instead.
    upload_dir = project_upload_dir(pid)
    dest = upload_dir / f"{fid}_a.txt"
    assert dest.exists()

    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{pid}")

    assert not upload_dir.exists()
