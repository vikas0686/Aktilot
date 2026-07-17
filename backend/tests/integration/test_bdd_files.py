"""
BDD-style, black-box API tests for /api/projects/{id}/files — pure HTTP in,
JSON out, no db_session/service pokes. See test_bdd_projects.py for the
shared rationale.

Temporal is mocked purely as an external-system boundary (no real worker in
this file, same seam tests/test_files.py already uses) — it isn't a
shortcut around the file API itself.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


def _mock_temporal():
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()
    return patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    )


async def _create_project(client, name: str = "P") -> str:
    return (await client.post("/api/projects", json={"name": name})).json()["id"]


async def _upload(client, project_id, filename="a.txt", content=b"content"):
    with _mock_temporal():
        return await client.post(
            f"/api/projects/{project_id}/files/upload",
            files={"file": (filename, io.BytesIO(content), "text/plain")},
        )


# ── Upload: success ───────────────────────────────────────────────────────────


async def test_upload_txt_file_succeeds(client):
    pid = await _create_project(client)
    r = await _upload(client, pid, "sample.txt", b"hello world")
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "sample.txt"
    assert body["size"] == len(b"hello world")
    assert body["project_id"] == pid
    assert body["chunk_status"] == "pending"
    assert body["chunk_count"] == 0
    assert "id" in body
    assert "uploaded_at" in body


@pytest.mark.parametrize("filename", ["doc.pdf", "doc.txt", "doc.doc", "doc.docx"])
async def test_upload_each_allowed_extension_succeeds(client, filename):
    pid = await _create_project(client)
    r = await _upload(client, pid, filename)
    assert r.status_code == 201, f"expected 201 for {filename}, got {r.status_code}"
    assert r.json()["filename"] == filename


@pytest.mark.parametrize("filename", ["DOC.PDF", "Report.TXT", "Notes.DocX"])
async def test_upload_extension_matching_is_case_insensitive(client, filename):
    pid = await _create_project(client)
    r = await _upload(client, pid, filename)
    assert r.status_code == 201


async def test_upload_empty_file_succeeds_with_size_zero(client):
    pid = await _create_project(client)
    r = await _upload(client, pid, "empty.txt", b"")
    assert r.status_code == 201
    assert r.json()["size"] == 0


async def test_upload_large_file_succeeds(client):
    pid = await _create_project(client)
    content = b"x" * (2 * 1024 * 1024)  # 2 MB
    r = await _upload(client, pid, "big.txt", content)
    assert r.status_code == 201
    assert r.json()["size"] == len(content)


async def test_upload_filename_with_unicode_round_trips(client):
    pid = await _create_project(client)
    r = await _upload(client, pid, "報告書.txt", b"content")
    assert r.status_code == 201
    assert r.json()["filename"] == "報告書.txt"


async def test_upload_two_files_to_same_project_get_distinct_ids(client):
    pid = await _create_project(client)
    a = await _upload(client, pid, "a.txt")
    b = await _upload(client, pid, "b.txt")
    assert a.json()["id"] != b.json()["id"]


async def test_upload_same_filename_twice_both_succeed_as_separate_records(client):
    pid = await _create_project(client)
    a = await _upload(client, pid, "same.txt")
    b = await _upload(client, pid, "same.txt")
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


# ── Upload: validation / failures ─────────────────────────────────────────────


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


async def test_upload_rejects_filename_with_no_extension(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={"file": ("README", io.BytesIO(b"content"), "text/plain")},
    )
    assert r.status_code == 400


async def test_upload_rejects_missing_project(client):
    r = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/files/upload",
        files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 404


async def test_upload_malformed_project_uuid_returns_422(client):
    r = await client.post(
        "/api/projects/not-a-uuid/files/upload",
        files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 422


async def test_upload_without_a_file_part_returns_422(client):
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/files/upload")
    assert r.status_code == 422


async def test_upload_rejects_double_extension_disguise(client):
    """`report.txt.exe` still ends in .exe — must still be rejected."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={
            "file": (
                "report.txt.exe",
                io.BytesIO(b"data"),
                "application/octet-stream",
            )
        },
    )
    assert r.status_code == 400


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_files_when_none_uploaded_returns_empty(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/files")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_files_project_not_found_returns_404(client):
    r = await client.get("/api/projects/00000000-0000-0000-0000-000000000000/files")
    assert r.status_code == 404


async def test_list_files_malformed_project_uuid_returns_422(client):
    r = await client.get("/api/projects/not-a-uuid/files")
    assert r.status_code == 422


async def test_list_files_returns_only_this_projects_files(client):
    pid1 = await _create_project(client, "P1")
    pid2 = await _create_project(client, "P2")
    a = (await _upload(client, pid1, "a.txt")).json()
    b = (await _upload(client, pid1, "b.txt")).json()
    await _upload(client, pid2, "c.txt")

    r = await client.get(f"/api/projects/{pid1}/files")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert {f["id"] for f in body} == {a["id"], b["id"]}


async def test_list_files_orders_most_recently_uploaded_first(client):
    pid = await _create_project(client)
    first = (await _upload(client, pid, "first.txt")).json()
    second = (await _upload(client, pid, "second.txt")).json()
    third = (await _upload(client, pid, "third.txt")).json()

    r = await client.get(f"/api/projects/{pid}/files")
    ids = [f["id"] for f in r.json()]
    assert ids == [third["id"], second["id"], first["id"]]


async def test_uploaded_file_appears_in_list_with_matching_metadata(client):
    pid = await _create_project(client)
    created = (await _upload(client, pid, "report.txt", b"hello world")).json()

    r = await client.get(f"/api/projects/{pid}/files")
    listed = next(f for f in r.json() if f["id"] == created["id"])
    assert listed == created


# ── Delete ────────────────────────────────────────────────────────────────────


async def test_delete_file_succeeds(client):
    pid = await _create_project(client)
    fid = (await _upload(client, pid)).json()["id"]
    with patch("services.project_file_service.chroma_delete_file"):
        r = await client.delete(f"/api/projects/{pid}/files/{fid}")
    assert r.status_code == 204


async def test_delete_file_removes_it_from_the_list(client):
    pid = await _create_project(client)
    fid = (await _upload(client, pid)).json()["id"]
    with patch("services.project_file_service.chroma_delete_file"):
        await client.delete(f"/api/projects/{pid}/files/{fid}")

    r = await client.get(f"/api/projects/{pid}/files")
    assert r.json() == []


async def test_delete_file_not_found_returns_404(client):
    pid = await _create_project(client)
    r = await client.delete(
        f"/api/projects/{pid}/files/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404


async def test_delete_file_malformed_uuid_returns_422(client):
    pid = await _create_project(client)
    r = await client.delete(f"/api/projects/{pid}/files/not-a-uuid")
    assert r.status_code == 422


async def test_delete_file_from_wrong_project_returns_404_and_survives(client):
    """A file belonging to project A must not be deletable through project
    B's route — mismatched project_id 404s, and the file survives."""
    pid_a = await _create_project(client, "A")
    pid_b = await _create_project(client, "B")
    fid = (await _upload(client, pid_a)).json()["id"]

    r = await client.delete(f"/api/projects/{pid_b}/files/{fid}")
    assert r.status_code == 404

    survivors = (await client.get(f"/api/projects/{pid_a}/files")).json()
    assert any(f["id"] == fid for f in survivors)


async def test_delete_file_twice_the_second_time_404s(client):
    pid = await _create_project(client)
    fid = (await _upload(client, pid)).json()["id"]
    with patch("services.project_file_service.chroma_delete_file"):
        first = await client.delete(f"/api/projects/{pid}/files/{fid}")
        second = await client.delete(f"/api/projects/{pid}/files/{fid}")
    assert first.status_code == 204
    assert second.status_code == 404


async def test_delete_one_file_does_not_affect_sibling_file(client):
    pid = await _create_project(client)
    keep = (await _upload(client, pid, "keep.txt")).json()
    remove = (await _upload(client, pid, "remove.txt")).json()

    with patch("services.project_file_service.chroma_delete_file"):
        await client.delete(f"/api/projects/{pid}/files/{remove['id']}")

    survivors = (await client.get(f"/api/projects/{pid}/files")).json()
    assert [f["id"] for f in survivors] == [keep["id"]]
