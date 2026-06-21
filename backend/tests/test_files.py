import io
from unittest.mock import AsyncMock, patch


async def _create_project(client, name: str = "P") -> str:
    return (await client.post("/api/projects", json={"name": name})).json()["id"]


def _txt_file(content: bytes = b"hello world", filename: str = "sample.txt"):
    return {"file": (filename, io.BytesIO(content), "text/plain")}


# ── Upload validation ─────────────────────────────────────────────────────────

async def test_upload_rejects_unsupported_extension(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={"file": ("malware.exe", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "Unsupported" in r.json()["detail"]


async def test_upload_rejects_missing_project(client):
    r = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/files/upload",
        files=_txt_file(),
    )
    assert r.status_code == 404


async def test_upload_allowed_extensions(client):
    pid = await _create_project(client)
    for filename in ("doc.pdf", "doc.txt", "doc.docx"):
        with patch("services.project_chunk_service.chunk_file", new_callable=AsyncMock):
            r = await client.post(
                f"/api/projects/{pid}/files/upload",
                files={"file": (filename, io.BytesIO(b"content"), "application/octet-stream")},
            )
        assert r.status_code == 201, f"Expected 201 for {filename}, got {r.status_code}"


# ── Upload success ────────────────────────────────────────────────────────────

async def test_upload_txt_returns_file_record(client):
    pid = await _create_project(client)
    with patch("services.project_chunk_service.chunk_file", new_callable=AsyncMock):
        r = await client.post(
            f"/api/projects/{pid}/files/upload",
            files=_txt_file(b"hello world"),
        )
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "sample.txt"
    assert body["size"] == 11
    assert body["project_id"] == pid
    assert "id" in body
    assert "uploaded_at" in body


async def test_upload_sets_pending_chunk_status(client):
    pid = await _create_project(client)
    with patch("services.project_chunk_service.chunk_file", new_callable=AsyncMock):
        r = await client.post(
            f"/api/projects/{pid}/files/upload",
            files=_txt_file(),
        )
    assert r.json()["chunk_status"] == "pending"


# ── List files ────────────────────────────────────────────────────────────────

async def test_list_files_empty(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/files")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_files_after_upload(client):
    pid = await _create_project(client)
    with patch("services.project_chunk_service.chunk_file", new_callable=AsyncMock):
        await client.post(f"/api/projects/{pid}/files/upload", files=_txt_file(filename="a.txt"))
        await client.post(f"/api/projects/{pid}/files/upload", files=_txt_file(filename="b.txt"))
    r = await client.get(f"/api/projects/{pid}/files")
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_list_files_project_not_found(client):
    r = await client.get("/api/projects/00000000-0000-0000-0000-000000000000/files")
    assert r.status_code == 404


# ── Delete file ───────────────────────────────────────────────────────────────

async def test_delete_file_not_found(client):
    pid = await _create_project(client)
    r = await client.delete(f"/api/projects/{pid}/files/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_delete_file_removes_it(client):
    pid = await _create_project(client)
    with patch("services.project_chunk_service.chunk_file", new_callable=AsyncMock):
        fid = (
            await client.post(f"/api/projects/{pid}/files/upload", files=_txt_file())
        ).json()["id"]

    with patch("services.project_file_service.chroma_delete_file"):
        r = await client.delete(f"/api/projects/{pid}/files/{fid}")
    assert r.status_code == 204

    files = (await client.get(f"/api/projects/{pid}/files")).json()
    assert all(f["id"] != fid for f in files)
