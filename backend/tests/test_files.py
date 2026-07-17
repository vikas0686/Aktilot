import io
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_temporal():
    """Return a patch that replaces get_temporal_client with a no-op mock."""
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()
    return patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    )


async def _create_project(client, name: str = "P") -> str:
    return (await client.post("/api/projects", json={"name": name})).json()["id"]


def _txt_file(content: bytes = b"hello world", filename: str = "sample.txt"):
    return {"file": (filename, io.BytesIO(content), "text/plain")}


# ── Upload validation ─────────────────────────────────────────────────────────


async def test_upload_rejects_unsupported_extension(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={
            "file": ("malware.exe", io.BytesIO(b"data"), "application/octet-stream")
        },
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
        with _mock_temporal():
            r = await client.post(
                f"/api/projects/{pid}/files/upload",
                files={
                    "file": (
                        filename,
                        io.BytesIO(b"content"),
                        "application/octet-stream",
                    )
                },
            )
        assert r.status_code == 201, f"Expected 201 for {filename}, got {r.status_code}"


async def test_upload_extension_check_is_case_insensitive(client):
    pid = await _create_project(client)
    with _mock_temporal():
        r = await client.post(
            f"/api/projects/{pid}/files/upload",
            files={"file": ("DOC.PDF", io.BytesIO(b"content"), "application/pdf")},
        )
    assert r.status_code == 201


async def test_upload_rejects_filename_with_no_extension(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={"file": ("README", io.BytesIO(b"content"), "text/plain")},
    )
    assert r.status_code == 400
    assert "Unsupported" in r.json()["detail"]


async def test_upload_accepts_empty_file(client):
    """A 0-byte upload is unusual but not invalid — it must not crash the
    route; it'll simply produce zero chunks downstream."""
    pid = await _create_project(client)
    with _mock_temporal():
        r = await client.post(
            f"/api/projects/{pid}/files/upload",
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        )
    assert r.status_code == 201
    assert r.json()["size"] == 0


# ── Upload success ────────────────────────────────────────────────────────────


async def test_upload_txt_returns_file_record(client):
    pid = await _create_project(client)
    with _mock_temporal():
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
    with _mock_temporal():
        r = await client.post(
            f"/api/projects/{pid}/files/upload",
            files=_txt_file(),
        )
    assert r.json()["chunk_status"] == "pending"


async def test_upload_triggers_workflow(client):
    """start_workflow must be called once per upload with the file id and project id."""
    pid = await _create_project(client)
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()
    with patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        r = await client.post(f"/api/projects/{pid}/files/upload", files=_txt_file())

    assert r.status_code == 201
    mock_client.start_workflow.assert_called_once()
    call_kwargs = mock_client.start_workflow.call_args
    # workflow id must embed the file id for idempotency
    file_id = r.json()["id"]
    assert call_kwargs.kwargs["id"] == f"doc-{file_id}"


# ── List files ────────────────────────────────────────────────────────────────


async def test_list_files_empty(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/files")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_files_after_upload(client):
    pid = await _create_project(client)
    with _mock_temporal():
        await client.post(
            f"/api/projects/{pid}/files/upload", files=_txt_file(filename="a.txt")
        )
        await client.post(
            f"/api/projects/{pid}/files/upload", files=_txt_file(filename="b.txt")
        )
    r = await client.get(f"/api/projects/{pid}/files")
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_list_files_project_not_found(client):
    r = await client.get("/api/projects/00000000-0000-0000-0000-000000000000/files")
    assert r.status_code == 404


# ── Delete file ───────────────────────────────────────────────────────────────


async def test_delete_file_not_found(client):
    pid = await _create_project(client)
    r = await client.delete(
        f"/api/projects/{pid}/files/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404


async def test_delete_file_removes_it(client):
    pid = await _create_project(client)
    with _mock_temporal():
        fid = (
            await client.post(f"/api/projects/{pid}/files/upload", files=_txt_file())
        ).json()["id"]

    with patch("services.project_file_service.chroma_delete_file"):
        r = await client.delete(f"/api/projects/{pid}/files/{fid}")
    assert r.status_code == 204

    files = (await client.get(f"/api/projects/{pid}/files")).json()
    assert all(f["id"] != fid for f in files)


async def test_delete_file_removes_it_from_disk(client):
    """Deleting a file must remove the underlying upload on disk, not just
    the DB row — mirrors the project-level disk-cleanup test."""
    pid = await _create_project(client)
    with _mock_temporal():
        fid = (
            await client.post(f"/api/projects/{pid}/files/upload", files=_txt_file())
        ).json()["id"]

    files = (await client.get(f"/api/projects/{pid}/files")).json()
    filename = next(f for f in files if f["id"] == fid)["filename"]
    from config import project_upload_dir

    dest = project_upload_dir(pid) / f"{fid}_{filename}"
    assert dest.exists()

    with patch("services.project_file_service.chroma_delete_file"):
        await client.delete(f"/api/projects/{pid}/files/{fid}")

    assert not dest.exists()


async def test_delete_file_wrong_project_returns_404_and_does_not_delete(client):
    """A file belonging to project A must not be deletable through project
    B's route — the mismatched project_id must 404, and the file must
    survive untouched."""
    pid_a = await _create_project(client, "A")
    pid_b = await _create_project(client, "B")
    with _mock_temporal():
        fid = (
            await client.post(f"/api/projects/{pid_a}/files/upload", files=_txt_file())
        ).json()["id"]

    r = await client.delete(f"/api/projects/{pid_b}/files/{fid}")
    assert r.status_code == 404

    files = (await client.get(f"/api/projects/{pid_a}/files")).json()
    assert any(f["id"] == fid for f in files)
