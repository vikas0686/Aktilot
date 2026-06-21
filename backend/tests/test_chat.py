from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from models.schemas import ChatResponse


async def _make_agent(client) -> tuple[str, str]:
    """Returns (project_id, agent_id)."""
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (await client.post(f"/api/projects/{pid}/agents", json={"name": "A"})).json()["id"]
    return pid, aid


_FAKE_RESPONSE = ChatResponse(
    answer="The answer is 42.",
    tool_steps=[],
    retrieved_chunks=[],
    keywords=["answer"],
)


# ── 404 guards ────────────────────────────────────────────────────────────────

async def test_chat_unknown_agent_returns_404(client):
    r = await client.post(
        "/api/agents/00000000-0000-0000-0000-000000000000/chat",
        json={"question": "Hello?"},
    )
    assert r.status_code == 404


async def test_messages_unknown_agent_returns_404(client):
    r = await client.get("/api/agents/00000000-0000-0000-0000-000000000000/messages")
    assert r.status_code == 404


async def test_chat_missing_question_returns_422(client):
    _, aid = await _make_agent(client)
    r = await client.post(f"/api/agents/{aid}/chat", json={})
    assert r.status_code == 422


# ── Message history ───────────────────────────────────────────────────────────

async def test_messages_empty_for_new_agent(client):
    _, aid = await _make_agent(client)
    r = await client.get(f"/api/agents/{aid}/messages")
    assert r.status_code == 200
    assert r.json() == []


# ── Chat response shape ───────────────────────────────────────────────────────

async def test_chat_returns_answer(client):
    _, aid = await _make_agent(client)
    with patch(
        "services.agent_rag_service.chat",
        new_callable=AsyncMock,
        return_value=_FAKE_RESPONSE,
    ):
        r = await client.post(f"/api/agents/{aid}/chat", json={"question": "What is 42?"})

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "The answer is 42."
    assert isinstance(body["tool_steps"], list)
    assert isinstance(body["retrieved_chunks"], list)
    assert isinstance(body["keywords"], list)


async def test_chat_passes_question_to_rag_service(client):
    _, aid = await _make_agent(client)
    with patch(
        "services.agent_rag_service.chat",
        new_callable=AsyncMock,
        return_value=_FAKE_RESPONSE,
    ) as mock_chat:
        await client.post(f"/api/agents/{aid}/chat", json={"question": "What is the deadline?"})

    # Verify the service was called with the right question
    call_args = mock_chat.call_args
    assert call_args.args[2] == "What is the deadline?"
