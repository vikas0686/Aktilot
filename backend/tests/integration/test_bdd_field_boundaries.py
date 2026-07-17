"""
BDD-style, black-box API tests focused on field-level boundary values across
resources — pure HTTP in, JSON out, no db_session/service pokes. Where the
other test_bdd_*.py files cover one representative case per behavior, this
file parametrizes across many concrete input values for the fields that
matter most: file extensions, numeric boundaries (top_k, daily_message_cap),
name edge cases, and UUID path-parameter formats.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


async def _create_project(client) -> str:
    return (await client.post("/api/projects", json={"name": "P"})).json()["id"]


async def _create_agent(client, project_id: str, **overrides) -> dict:
    payload = {"name": "Agent"}
    payload.update(overrides)
    return (
        await client.post(f"/api/projects/{project_id}/agents", json=payload)
    ).json()


def _mock_temporal():
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()
    return patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    )


# ── File extensions: rejected ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename",
    [
        "malware.exe",
        "script.sh",
        "batch.bat",
        "code.js",
        "code.py",
        "archive.zip",
        "image.png",
        "photo.jpg",
        "video.mp4",
        "data.csv",
        "sheet.xlsx",
        "page.html",
        "styles.css",
        "archive.tar.gz",
    ],
)
async def test_upload_rejects_each_unsupported_extension(client, filename):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={"file": (filename, io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert r.status_code == 400, f"expected 400 for {filename}, got {r.status_code}"


@pytest.mark.parametrize(
    "filename", ["README", "Makefile", "noext", ".hidden", "trailing."]
)
async def test_upload_rejects_each_no_or_edge_extension_filename(client, filename):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/files/upload",
        files={"file": (filename, io.BytesIO(b"data"), "text/plain")},
    )
    assert r.status_code == 400, f"expected 400 for {filename!r}, got {r.status_code}"


@pytest.mark.parametrize(
    "filename",
    ["a.pdf", "a.txt", "a.doc", "a.docx", "A.PDF", "A.TXT", "A.DOC", "A.DOCX"],
)
async def test_upload_accepts_each_allowed_extension_any_case(client, filename):
    pid = await _create_project(client)
    with _mock_temporal():
        r = await client.post(
            f"/api/projects/{pid}/files/upload",
            files={"file": (filename, io.BytesIO(b"data"), "text/plain")},
        )
    assert r.status_code == 201, f"expected 201 for {filename}, got {r.status_code}"


# ── top_k boundaries ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("top_k", [1, 2, 3, 5, 10])
async def test_create_agent_accepts_each_documented_valid_top_k(client, top_k):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": top_k}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == top_k


@pytest.mark.parametrize("top_k", [0, -1, -10, 100, 1000])
async def test_create_agent_top_k_outside_documented_range_is_currently_accepted(
    client, top_k
):
    """Known gap: no server-side bounds check on top_k (the frontend clamps
    1-10 client-side only)."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": top_k}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == top_k


@pytest.mark.parametrize("top_k", [1.5, None, [1, 2], {"k": 1}, "not-a-number"])
async def test_create_agent_non_integer_top_k_returns_422(client, top_k):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": top_k}
    )
    assert r.status_code == 422, (
        f"expected 422 for top_k={top_k!r}, got {r.status_code}"
    )


async def test_create_agent_top_k_as_numeric_string_is_coerced_and_accepted(client):
    """Pydantic's lax mode coerces numeric strings to int for int fields —
    "3" is valid input here, not a validation error."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/agents", json={"name": "Bot", "top_k": "3"}
    )
    assert r.status_code == 201
    assert r.json()["top_k"] == 3


# ── daily_message_cap boundaries ──────────────────────────────────────────────


@pytest.mark.parametrize("cap", [1, 2, 10, 100, 1000, 100000])
async def test_generate_share_link_accepts_each_positive_cap(client, cap):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": cap})
    assert r.status_code == 200
    assert r.json()["daily_message_cap"] == cap


@pytest.mark.parametrize("cap", [0, -1, -10, -100000])
async def test_generate_share_link_rejects_each_non_positive_cap(client, cap):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": cap})
    assert r.status_code == 422, f"expected 422 for cap={cap}, got {r.status_code}"


@pytest.mark.parametrize("cap", [1.5, "many", [1], {"cap": 1}])
async def test_generate_share_link_rejects_each_non_integer_cap(client, cap):
    pid = await _create_project(client)
    aid = (await _create_agent(client, pid))["id"]
    r = await client.post(f"/api/agents/{aid}/share", json={"daily_message_cap": cap})
    assert r.status_code == 422


# ── Name edge cases (shared shape across projects/agents) ────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "A",  # single character
        "1234567890",  # digits only
        "Name\twith\ttabs",
        "Name\nwith\nnewlines",
        "   leading and trailing   ",
        "Iñtërnâtiônàlizætiøn",
        "😀😃😄 emoji name",
        "混合 mixed 言語",
    ],
)
async def test_create_project_accepts_each_name_edge_case_and_round_trips_it(
    client, name
):
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201
    assert r.json()["name"] == name

    got = (await client.get(f"/api/projects/{r.json()['id']}")).json()
    assert got["name"] == name


@pytest.mark.parametrize(
    "name",
    [
        "A",
        "1234567890",
        "Iñtërnâtiônàlizætiøn",
        "😀😃😄 emoji name",
    ],
)
async def test_create_agent_accepts_each_name_edge_case_and_round_trips_it(
    client, name
):
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/agents", json={"name": name})
    assert r.status_code == 201
    assert r.json()["name"] == name


# ── UUID path-parameter format variants ───────────────────────────────────────


async def test_get_project_uuid_with_uppercase_hex_digits_is_accepted(client):
    """Python's uuid.UUID() parsing is case-insensitive — confirms the path
    param behaves the same way, not that it's case-sensitive by accident."""
    project_id = await _create_project(client)
    r = await client.get(f"/api/projects/{project_id.upper()}")
    assert r.status_code == 200
    assert r.json()["id"] == project_id


@pytest.mark.parametrize(
    "malformed",
    [
        "12345",
        "not-a-uuid-at-all",
        "00000000-0000-0000-0000-00000000000",  # one digit short
        "00000000-0000-0000-0000-0000000000000",  # one digit too many
        "gggggggg-gggg-gggg-gggg-gggggggggggg",  # invalid hex chars
    ],
)
async def test_get_project_rejects_each_malformed_uuid_shape(client, malformed):
    r = await client.get(f"/api/projects/{malformed}")
    assert r.status_code in (404, 422), (
        f"expected 404 or 422 for {malformed!r}, got {r.status_code}"
    )


async def test_get_project_with_empty_id_segment_hits_the_slash_redirect_not_404(
    client,
):
    """`/api/projects/` (empty id segment) matches the collection route's
    trailing-slash form before it ever reaches path-param UUID parsing —
    it 307-redirects to the list endpoint, it doesn't 404 or 422."""
    r = await client.get("/api/projects/", follow_redirects=False)
    assert r.status_code == 307


async def test_get_project_uuid_with_braces_is_accepted(client):
    """Python's uuid.UUID() strips {} and urn:uuid: — the path param
    inherits that permissiveness."""
    created = await _create_project(client)
    braced = "{" + created + "}"
    r = await client.get(f"/api/projects/{braced}")
    assert r.status_code == 200
    assert r.json()["id"] == created


# ── Scale: ordering holds beyond three items ──────────────────────────────────


async def test_project_list_ordering_holds_for_ten_projects(client):
    created = []
    for i in range(10):
        r = await client.post("/api/projects", json={"name": f"Project {i}"})
        created.append(r.json())

    r = await client.get("/api/projects")
    ids = [p["id"] for p in r.json()]
    assert ids == [p["id"] for p in reversed(created)]


async def test_agent_list_ordering_holds_for_ten_agents(client):
    pid = await _create_project(client)
    created = []
    for i in range(10):
        created.append(await _create_agent(client, pid, name=f"Agent {i}"))

    r = await client.get(f"/api/projects/{pid}/agents")
    ids = [a["id"] for a in r.json()]
    assert ids == [a["id"] for a in created]


async def test_file_list_contains_all_of_twenty_uploads(client):
    pid = await _create_project(client)
    uploaded_ids = set()
    with _mock_temporal():
        for i in range(20):
            r = await client.post(
                f"/api/projects/{pid}/files/upload",
                files={"file": (f"file{i}.txt", io.BytesIO(b"x"), "text/plain")},
            )
            uploaded_ids.add(r.json()["id"])

    r = await client.get(f"/api/projects/{pid}/files")
    listed_ids = {f["id"] for f in r.json()}
    assert listed_ids == uploaded_ids
    assert len(r.json()) == 20
