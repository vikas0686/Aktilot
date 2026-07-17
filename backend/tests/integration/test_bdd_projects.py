"""
BDD-style, black-box API tests for /api/projects — every test only calls
real HTTP endpoints (the `client` fixture: real FastAPI routing, real
in-memory SQLite, nothing mocked at the DB layer) and only asserts on JSON
responses. No db_session/service-layer pokes anywhere in this file.

Split out from test_api_http_flows.py so each resource's full success +
failure + edge-case matrix lives in its own file.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


async def _create(client, **overrides) -> dict:
    payload = {"name": "Project"}
    payload.update(overrides)
    return (await client.post("/api/projects", json=payload)).json()


# ── Create: success ───────────────────────────────────────────────────────────


async def test_create_project_with_minimal_fields_succeeds(client):
    """
    Given only a name
    When POST /api/projects is called
    Then a project is created with description=None
    """
    r = await client.post("/api/projects", json={"name": "Alpha"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Alpha"
    assert body["description"] is None
    assert "id" in body
    assert "created_at" in body


async def test_create_project_with_description_succeeds(client):
    r = await client.post(
        "/api/projects", json={"name": "Legal", "description": "Legal docs"}
    )
    assert r.status_code == 201
    assert r.json()["description"] == "Legal docs"


async def test_create_project_description_explicit_null_succeeds(client):
    r = await client.post("/api/projects", json={"name": "P", "description": None})
    assert r.status_code == 201
    assert r.json()["description"] is None


async def test_create_project_unknown_extra_fields_are_ignored(client):
    r = await client.post(
        "/api/projects", json={"name": "P", "unexpected_field": "whatever"}
    )
    assert r.status_code == 201
    assert "unexpected_field" not in r.json()


async def test_create_project_two_different_ids_for_two_calls(client):
    """Two projects created with the same name must still get distinct ids."""
    a = await _create(client, name="Same Name")
    b = await _create(client, name="Same Name")
    assert a["id"] != b["id"]


# ── Create: validation edge cases ─────────────────────────────────────────────


async def test_create_project_missing_name_returns_422(client):
    r = await client.post("/api/projects", json={})
    assert r.status_code == 422


async def test_create_project_null_name_returns_422(client):
    r = await client.post("/api/projects", json={"name": None})
    assert r.status_code == 422


async def test_create_project_non_string_name_returns_422(client):
    r = await client.post("/api/projects", json={"name": 12345})
    assert r.status_code == 422


async def test_create_project_empty_body_returns_422(client):
    r = await client.post("/api/projects", content=b"")
    assert r.status_code == 422


async def test_create_project_empty_name_is_currently_accepted(client):
    """Known gap: ProjectCreate.name has no min_length constraint."""
    r = await client.post("/api/projects", json={"name": ""})
    assert r.status_code == 201
    assert r.json()["name"] == ""


async def test_create_project_whitespace_only_name_is_currently_accepted(client):
    r = await client.post("/api/projects", json={"name": "   "})
    assert r.status_code == 201


async def test_create_project_very_long_name_is_currently_accepted(client):
    """Known gap: no max_length either."""
    long_name = "A" * 5000
    r = await client.post("/api/projects", json={"name": long_name})
    assert r.status_code == 201
    assert r.json()["name"] == long_name


async def test_create_project_unicode_name_round_trips_exactly(client):
    name = "日本語\U0001f680 Projekt"
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201
    assert r.json()["name"] == name


async def test_create_project_name_with_special_characters_round_trips(client):
    name = "Project <script>alert(1)</script> & \"quotes\" 'more'"
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201
    assert r.json()["name"] == name


# ── Get ───────────────────────────────────────────────────────────────────────


async def test_get_existing_project_returns_it(client):
    created = await _create(client, name="Gamma")
    r = await client.get(f"/api/projects/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


async def test_get_project_with_valid_uuid_but_no_match_returns_404(client):
    r = await client.get("/api/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_get_project_with_malformed_uuid_returns_422(client):
    r = await client.get("/api/projects/not-a-valid-uuid")
    assert r.status_code == 422


async def test_get_project_after_it_was_deleted_returns_404(client):
    created = await _create(client)
    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{created['id']}")

    r = await client.get(f"/api/projects/{created['id']}")
    assert r.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_projects_when_none_exist_returns_empty_list(client):
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_projects_returns_the_one_created(client):
    created = await _create(client, name="Solo")
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == [created]


async def test_list_projects_returns_all_created_ones(client):
    await _create(client, name="One")
    await _create(client, name="Two")
    await _create(client, name="Three")
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert len(r.json()) == 3
    names = {p["name"] for p in r.json()}
    assert names == {"One", "Two", "Three"}


async def test_list_projects_orders_most_recently_created_first(client):
    first = await _create(client, name="First")
    second = await _create(client, name="Second")
    third = await _create(client, name="Third")

    r = await client.get("/api/projects")
    ids = [p["id"] for p in r.json()]
    assert ids == [third["id"], second["id"], first["id"]]


# ── Delete ────────────────────────────────────────────────────────────────────


async def test_delete_existing_project_succeeds(client):
    created = await _create(client)
    with patch("services.project_service.chroma_delete_project"):
        r = await client.delete(f"/api/projects/{created['id']}")
    assert r.status_code == 204


async def test_delete_project_removes_it_from_the_list(client):
    created = await _create(client)
    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{created['id']}")

    r = await client.get("/api/projects")
    assert r.json() == []


async def test_delete_project_not_found_returns_404(client):
    with patch("services.project_service.chroma_delete_project"):
        r = await client.delete("/api/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_delete_project_with_malformed_uuid_returns_422(client):
    r = await client.delete("/api/projects/not-a-uuid")
    assert r.status_code == 422


async def test_deleting_the_same_project_twice_the_second_time_404s(client):
    created = await _create(client)
    with patch("services.project_service.chroma_delete_project"):
        first = await client.delete(f"/api/projects/{created['id']}")
        second = await client.delete(f"/api/projects/{created['id']}")
    assert first.status_code == 204
    assert second.status_code == 404


async def test_deleting_one_project_does_not_affect_another(client):
    a = await _create(client, name="Keep")
    b = await _create(client, name="Remove")
    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{b['id']}")

    r = await client.get(f"/api/projects/{a['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Keep"


# ── Delete: cascades ──────────────────────────────────────────────────────────


async def test_deleting_project_makes_its_agent_unreachable(client):
    project = await _create(client)
    aid = (
        await client.post(f"/api/projects/{project['id']}/agents", json={"name": "A"})
    ).json()["id"]

    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{project['id']}")

    assert (await client.get(f"/api/agents/{aid}")).status_code == 404


async def test_deleting_project_makes_its_files_listing_unreachable(client):
    project = await _create(client)
    mock_tc = MagicMock()
    mock_tc.start_workflow = AsyncMock()
    with patch(
        "api.routes.project_files.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        await client.post(
            f"/api/projects/{project['id']}/files/upload",
            files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
        )

    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{project['id']}")

    assert (await client.get(f"/api/projects/{project['id']}/files")).status_code == 404


async def test_deleting_project_makes_its_agent_sessions_unreachable(client):
    project = await _create(client)
    aid = (
        await client.post(f"/api/projects/{project['id']}/agents", json={"name": "A"})
    ).json()["id"]
    sid = (await client.post(f"/api/agents/{aid}/sessions")).json()["id"]

    with patch("services.project_service.chroma_delete_project"):
        await client.delete(f"/api/projects/{project['id']}")

    assert (await client.get(f"/api/agents/{aid}/sessions")).status_code == 404
    assert (await client.get(f"/api/sessions/{sid}/messages")).status_code == 404


async def test_deleting_project_calls_chroma_delete_project_with_its_id(client):
    project = await _create(client)
    with patch("services.project_service.chroma_delete_project") as mock_delete:
        await client.delete(f"/api/projects/{project['id']}")
    mock_delete.assert_called_once_with(project["id"])
