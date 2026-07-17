"""
Unit tests for temporal/activities/chat_activities.py.

Activities are plain async functions and can be called directly — except the
ones that read `activity.info()` for observability attributes (extract_keywords,
embed_query, search_vectors, hybrid_rank, generate_answer), which need a fake
activity context. `ActivityEnvironment` from temporalio.testing provides that.
Each test patches only the external dependency under test.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from services.llm.base import (
    ChatResult,
    EmbedResult,
    ProviderAuthError,
    ProviderServiceError,
)
from temporal.activities.chat_activities import (
    embed_query,
    extract_keywords,
    generate_answer,
    get_agent_config,
    hybrid_rank,
    search_vectors,
)

_env = ActivityEnvironment()

# ── Helpers ───────────────────────────────────────────────────────────────────

FAKE_VECTOR = [0.1] * 10

FAKE_CHUNKS = [
    {
        "id": "c1",
        "content": "The invoice total is $500.",
        "metadata": {"filename": "inv.txt", "chunk_index": 0},
        "distance": 0.1,
    },
    {
        "id": "c2",
        "content": "Payment due by January 31.",
        "metadata": {"filename": "inv.txt", "chunk_index": 1},
        "distance": 0.4,
    },
]


def _chat_result(content: str, prompt=10, completion=5) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        finish_reason="stop",
    )


def _embed_result(vector: list[float], tokens=10) -> EmbedResult:
    return EmbedResult(embeddings=[vector], total_tokens=tokens)


def _mock_chat_provider(return_value=None, side_effect=None):
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=return_value, side_effect=side_effect)
    factory = MagicMock(return_value=provider)
    return factory


def _mock_embedding_provider(return_value=None, side_effect=None):
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=return_value, side_effect=side_effect)
    factory = MagicMock(return_value=provider)
    return factory


def _mock_db_factory(agent=None):
    """Return a patch for AsyncSessionFactory that yields a mock DB session."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = agent
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


# ── extract_keywords ──────────────────────────────────────────────────────────


async def test_extract_keywords_returns_list():
    factory = _mock_chat_provider(
        return_value=_chat_result(json.dumps(["invoice", "total"]))
    )
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        result = await _env.run(extract_keywords, "What is the invoice total?")

    assert result == ["invoice", "total"]


async def test_extract_keywords_fallback_on_bad_json():
    factory = _mock_chat_provider(return_value=_chat_result("not valid json"))
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        result = await _env.run(extract_keywords, "find the invoice")

    assert result == ["find", "the", "invoice"]


async def test_extract_keywords_auth_error_raises_non_retryable():
    factory = _mock_chat_provider(side_effect=ProviderAuthError("Invalid API key"))
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(extract_keywords, "test?")

    assert exc.value.type == "AUTH_ERROR"
    assert exc.value.non_retryable is True


async def test_extract_keywords_rate_limit_raises_retryable():
    factory = _mock_chat_provider(
        side_effect=ProviderServiceError("Rate limit", reason="rate_limit")
    )
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(extract_keywords, "test?")

    assert exc.value.type == "RATE_LIMIT"
    assert exc.value.non_retryable is False


# ── embed_query ───────────────────────────────────────────────────────────────


async def test_embed_query_returns_vector():
    factory = _mock_embedding_provider(return_value=_embed_result(FAKE_VECTOR))
    with patch("temporal.activities.chat_activities.get_embedding_provider", factory):
        result = await _env.run(embed_query, "What is the total?")

    assert result == FAKE_VECTOR
    assert len(result) == 10


async def test_embed_query_auth_error_raises_non_retryable():
    factory = _mock_embedding_provider(side_effect=ProviderAuthError("Invalid API key"))
    with patch("temporal.activities.chat_activities.get_embedding_provider", factory):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(embed_query, "test")

    assert exc.value.type == "AUTH_ERROR"
    assert exc.value.non_retryable is True


# ── search_vectors ────────────────────────────────────────────────────────────


async def test_search_vectors_delegates_to_chroma_search():
    with patch(
        "temporal.activities.chat_activities.chroma_search",
        return_value=FAKE_CHUNKS,
    ) as mock_search:
        result = await _env.run(search_vectors, "proj-1", FAKE_VECTOR, ["invoice"])

    mock_search.assert_called_once_with("proj-1", FAKE_VECTOR, k=20)
    assert result == FAKE_CHUNKS


# ── hybrid_rank ───────────────────────────────────────────────────────────────


async def test_hybrid_rank_empty_results_returns_empty():
    result = await _env.run(hybrid_rank, [], ["invoice"], 5)
    assert result == []


async def test_hybrid_rank_score_is_half_vec_half_bm25():
    result = await _env.run(hybrid_rank, FAKE_CHUNKS, ["invoice"], 10)
    for chunk in result:
        expected = round(0.5 * chunk["vec_score"] + 0.5 * chunk["bm25_score"], 4)
        assert chunk["score"] == pytest.approx(expected, abs=1e-4)


async def test_hybrid_rank_limits_to_top_k():
    result = await _env.run(hybrid_rank, FAKE_CHUNKS, ["invoice"], 1)
    assert len(result) == 1


async def test_hybrid_rank_sorted_descending_by_score():
    result = await _env.run(hybrid_rank, FAKE_CHUNKS, ["invoice", "total"], 10)
    scores = [c["score"] for c in result]
    assert scores == sorted(scores, reverse=True)


async def test_hybrid_rank_vec_score_is_one_minus_distance():
    # chunk c1 has distance=0.1 → vec_score = 0.9
    result = await _env.run(hybrid_rank, FAKE_CHUNKS, [], 10)
    by_id = {c["chunk_id"]: c for c in result}
    assert by_id["c1"]["vec_score"] == pytest.approx(0.9, abs=1e-4)
    assert by_id["c2"]["vec_score"] == pytest.approx(0.6, abs=1e-4)


# ── generate_answer ───────────────────────────────────────────────────────────


async def test_generate_answer_returns_string():
    factory = _mock_chat_provider(return_value=_chat_result("The total is $500."))
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        result = await _env.run(
            generate_answer,
            "What is the total?",
            "CONTEXT: $500.",
            "Answer from context.",
        )

    assert result == "The total is $500."


async def test_generate_answer_auth_error_raises_non_retryable():
    factory = _mock_chat_provider(side_effect=ProviderAuthError("Invalid API key"))
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(generate_answer, "?", "ctx", "sys")

    assert exc.value.type == "AUTH_ERROR"
    assert exc.value.non_retryable is True


async def test_generate_answer_rate_limit_raises_retryable():
    factory = _mock_chat_provider(
        side_effect=ProviderServiceError("Rate limit", reason="rate_limit")
    )
    with patch("temporal.activities.chat_activities.get_chat_provider", factory):
        with pytest.raises(ApplicationError) as exc:
            await _env.run(generate_answer, "?", "ctx", "sys")

    assert exc.value.type == "RATE_LIMIT"
    assert exc.value.non_retryable is False


# ── get_agent_config ──────────────────────────────────────────────────────────


async def test_get_agent_config_missing_agent_raises_not_found():
    factory = _mock_db_factory(agent=None)
    with patch("temporal.activities.chat_activities.AsyncSessionFactory", factory):
        with pytest.raises(ApplicationError) as exc:
            await get_agent_config("00000000-0000-0000-0000-000000000000")

    assert exc.value.type == "NOT_FOUND"
    assert exc.value.non_retryable is True


async def test_get_agent_config_uses_fallback_prompt_when_blank():
    mock_agent = MagicMock()
    mock_agent.project_id = "proj-1"
    mock_agent.system_prompt = "   "  # whitespace only → triggers fallback
    mock_agent.top_k = 3

    factory = _mock_db_factory(agent=mock_agent)
    with patch("temporal.activities.chat_activities.AsyncSessionFactory", factory):
        from temporal.activities.chat_activities import _FALLBACK_SYSTEM_PROMPT

        config = await get_agent_config("00000000-0000-0000-0000-000000000001")

    assert config["system_prompt"] == _FALLBACK_SYSTEM_PROMPT
    assert config["top_k"] == 3


async def test_get_agent_config_returns_fields():
    mock_agent = MagicMock()
    mock_agent.project_id = "proj-99"
    mock_agent.system_prompt = "Be concise."
    mock_agent.top_k = 5

    factory = _mock_db_factory(agent=mock_agent)
    with patch("temporal.activities.chat_activities.AsyncSessionFactory", factory):
        config = await get_agent_config("00000000-0000-0000-0000-000000000002")

    assert config["project_id"] == "proj-99"
    assert config["system_prompt"] == "Be concise."
    assert config["top_k"] == 5
