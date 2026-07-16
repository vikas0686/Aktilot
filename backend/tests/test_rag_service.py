"""
Integration tests for agent_rag_service.chat:
  - Happy path: returns ChatResponse, hybrid scoring, pipeline steps
  - Keyword JSON parse fallback
  - Empty vector results
  - Fallback system prompt when agent.system_prompt is blank
  - Message persistence after successful chat
  - Cascade: deleting an agent removes its messages
  - Error handling: ProviderAuthError → 401, ProviderServiceError → 429, generic → 500

Each test uses a real in-memory SQLite DB (db_session fixture from conftest).
Only provider calls and ChromaDB calls are mocked.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.llm.base import (
    ChatResult,
    EmbedResult,
    ProviderAuthError,
    ProviderServiceError,
)
from services.agent_rag_service import _FALLBACK_SYSTEM_PROMPT, chat as rag_chat
from services.agent_service import create as create_agent
from services.agent_service import delete as delete_agent
from services.message_service import create as create_message
from services.message_service import list_for_agent
from services.project_service import create as create_project


# ── Helpers ───────────────────────────────────────────────────────────────────


FAKE_VECTOR = [0.1] * 10

FAKE_CHUNKS = [
    {
        "id": "chunk-1",
        "content": "The invoice total is $500.",
        "metadata": {"filename": "invoice.txt", "chunk_index": 0},
        "distance": 0.1,  # cosine distance → vec_score = 0.9
    },
    {
        "id": "chunk-2",
        "content": "Payment due by January 31.",
        "metadata": {"filename": "invoice.txt", "chunk_index": 1},
        "distance": 0.4,  # → vec_score = 0.6
    },
]


def _chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        finish_reason="stop",
    )


def _embed_result(vector: list[float]) -> EmbedResult:
    return EmbedResult(embeddings=[vector], total_tokens=10)


def _mock_providers(chat_side_effect=None, embed_return=None):
    """Return patches for get_chat_provider and get_embedding_provider."""
    chat_provider = MagicMock()
    chat_provider.generate = AsyncMock(side_effect=chat_side_effect)

    embed_provider = MagicMock()
    embed_provider.embed = AsyncMock(
        return_value=embed_return or _embed_result(FAKE_VECTOR)
    )

    chat_factory = MagicMock(return_value=chat_provider)
    embed_factory = MagicMock(return_value=embed_provider)

    return (
        patch("services.agent_rag_service.get_chat_provider", chat_factory),
        patch("services.agent_rag_service.get_embedding_provider", embed_factory),
        chat_provider,
    )


# ── Fixture: project + agent in the test DB ───────────────────────────────────


async def _setup(
    db_session, system_prompt: str = "Answer from context.", top_k: int = 2
):
    project = await create_project(db_session, "Test Project", None)
    agent = await create_agent(
        db_session, project.id, "Bot", None, system_prompt, top_k
    )
    return project, agent


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_chat_returns_chat_response(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, chat_prov = _mock_providers(
        chat_side_effect=[
            _chat_result(json.dumps(["invoice", "total"])),
            _chat_result("$500."),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        result = await rag_chat(db_session, agent.id, "What is the invoice total?")

    assert result.answer == "$500."
    assert result.keywords == ["invoice", "total"]
    assert len(result.tool_steps) == 5  # 5 named pipeline steps
    assert len(result.retrieved_chunks) == 2  # top_k=2, both chunks returned


async def test_chat_pipeline_step_names(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[
            _chat_result(json.dumps(["invoice"])),
            _chat_result("Answer."),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        result = await rag_chat(db_session, agent.id, "What?")

    step_names = [s.name for s in result.tool_steps]
    assert step_names == [
        "Extract Keywords",
        "Vector Search",
        "BM25 + Hybrid Rank",
        "Build Context",
        "Generate Answer",
    ]


# ── Hybrid scoring ────────────────────────────────────────────────────────────


async def test_chat_vec_score_is_one_minus_distance(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[_chat_result(json.dumps(["invoice"])), _chat_result("x")],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        result = await rag_chat(db_session, agent.id, "What?")

    # chunk-1: distance=0.1  → vec_score = round(1.0 - 0.1, 4) = 0.9
    # chunk-2: distance=0.4  → vec_score = round(1.0 - 0.4, 4) = 0.6
    scores = {c.chunk_id: c.vec_score for c in result.retrieved_chunks}
    assert scores["chunk-1"] == pytest.approx(0.9, abs=1e-4)
    assert scores["chunk-2"] == pytest.approx(0.6, abs=1e-4)


async def test_chat_final_score_is_hybrid(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[_chat_result(json.dumps(["invoice"])), _chat_result("x")],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        result = await rag_chat(db_session, agent.id, "What?")

    for chunk in result.retrieved_chunks:
        expected = round(0.5 * chunk.vec_score + 0.5 * chunk.bm25_score, 4)
        assert chunk.score == pytest.approx(expected, abs=1e-4)


async def test_chat_higher_vec_score_ranks_first(db_session):
    # chunk-1 has distance=0.1 (vec_score=0.9), chunk-2 has distance=0.4 (vec_score=0.6)
    # both have content matching the keyword "invoice" differently — but vec dominates
    # as long as chunk-1 vec+bm25 > chunk-2 vec+bm25
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[
            _chat_result(json.dumps(["invoice", "total"])),
            _chat_result("x"),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        result = await rag_chat(db_session, agent.id, "invoice total?")

    assert result.retrieved_chunks[0].chunk_id == "chunk-1"


async def test_chat_top_k_limits_returned_chunks(db_session):
    _, agent = await _setup(db_session, top_k=1)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[_chat_result(json.dumps(["x"])), _chat_result("y")],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        result = await rag_chat(db_session, agent.id, "?")

    assert len(result.retrieved_chunks) == 1  # top_k=1


# ── Edge cases ────────────────────────────────────────────────────────────────


async def test_chat_keyword_json_parse_fallback(db_session):
    """When provider returns invalid JSON for keywords, fall back to question.split()."""
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[
            _chat_result("not valid json at all"),
            _chat_result("no results"),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=[]),
    ):
        result = await rag_chat(db_session, agent.id, "find invoice")

    # Fallback: question.lower().split()
    assert result.keywords == ["find", "invoice"]


async def test_chat_empty_chroma_results(db_session):
    """With no vectors in the collection, retrieved_chunks is empty."""
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[
            _chat_result(json.dumps(["nothing"])),
            _chat_result("I could not find that."),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=[]),
    ):
        result = await rag_chat(db_session, agent.id, "nothing?")

    assert result.retrieved_chunks == []
    assert result.answer == "I could not find that."


async def test_chat_uses_fallback_system_prompt_when_blank(db_session):
    """An agent with an empty system_prompt should use _FALLBACK_SYSTEM_PROMPT."""
    _, agent = await _setup(db_session, system_prompt="")
    chat_patch, embed_patch, chat_prov = _mock_providers(
        chat_side_effect=[
            _chat_result(json.dumps([])),
            _chat_result("fallback answer"),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=[]),
    ):
        await rag_chat(db_session, agent.id, "hello?")

    # The second call to generate (step 5) passes the system message
    answer_call_messages = chat_prov.generate.call_args_list[1].kwargs["messages"]
    system_msg = next(m for m in answer_call_messages if m["role"] == "system")
    assert system_msg["content"] == _FALLBACK_SYSTEM_PROMPT


# ── Message persistence ───────────────────────────────────────────────────────


async def test_chat_persists_user_and_assistant_messages(db_session):
    """A successful chat must save exactly two messages: user then assistant."""
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=[
            _chat_result(json.dumps(["invoice"])),
            _chat_result("The total is $500."),
        ],
    )
    with (
        chat_patch,
        embed_patch,
        patch("services.agent_rag_service.chroma_search", return_value=FAKE_CHUNKS),
    ):
        await rag_chat(db_session, agent.id, "What is the invoice total?")

    messages = await list_for_agent(db_session, agent.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "What is the invoice total?"
    assert messages[1].role == "assistant"
    assert messages[1].content == "The total is $500."


async def test_chat_does_not_persist_messages_on_error(db_session):
    """If the RAG pipeline fails, no messages should be written."""
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=ProviderAuthError("Invalid API key"),
    )
    with chat_patch, embed_patch:
        with pytest.raises(HTTPException):
            await rag_chat(db_session, agent.id, "Test?")

    messages = await list_for_agent(db_session, agent.id)
    assert messages == []


# ── Cascade: agent deletion removes messages ──────────────────────────────────


async def test_delete_agent_removes_its_messages(db_session):
    """Messages cascade-delete when their parent agent is deleted."""
    _, agent = await _setup(db_session)
    await create_message(db_session, agent.id, "user", "Hello?")
    await create_message(db_session, agent.id, "assistant", "Hi there.")

    messages_before = await list_for_agent(db_session, agent.id)
    assert len(messages_before) == 2

    await delete_agent(db_session, agent.id)

    from db.models.message import Message
    from sqlalchemy import select

    result = await db_session.execute(
        select(Message).where(Message.agent_id == agent.id)
    )
    assert result.scalars().all() == []


# ── Error handling ────────────────────────────────────────────────────────────


async def test_chat_auth_error_raises_401(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=ProviderAuthError("Invalid API key"),
    )
    with chat_patch, embed_patch:
        with pytest.raises(HTTPException) as exc:
            await rag_chat(db_session, agent.id, "Test?")

    assert exc.value.status_code == 401


async def test_chat_rate_limit_raises_429(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=ProviderServiceError("Rate limit exceeded"),
    )
    with chat_patch, embed_patch:
        with pytest.raises(HTTPException) as exc:
            await rag_chat(db_session, agent.id, "Test?")

    assert exc.value.status_code == 429


async def test_chat_generic_exception_raises_500(db_session):
    _, agent = await _setup(db_session)
    chat_patch, embed_patch, _ = _mock_providers(
        chat_side_effect=RuntimeError("unexpected failure"),
    )
    with chat_patch, embed_patch:
        with pytest.raises(HTTPException) as exc:
            await rag_chat(db_session, agent.id, "Test?")

    assert exc.value.status_code == 500
