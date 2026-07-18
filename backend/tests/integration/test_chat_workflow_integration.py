"""
Full-stack integration tests for the RAG chat pipeline.

These drive the real HTTP routes, which dispatch to a REAL ChatWorkflow
running on a REAL (ephemeral, time-skipping) Temporal server, executed by a
REAL Worker running the REAL activities against the REAL (in-memory) database.
Only the LLM provider calls and the ChromaDB vector search are scripted —
see tests/integration/conftest.py for the exact boundary and why.

This is deliberately the "missing middle" between:
  - tests/test_chat.py           — stubs the whole workflow away
  - tests/test_chat_activities.py — calls each activity function in isolation
"""

import pytest
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError

from services.llm.base import ProviderAuthError, ProviderServiceError
from temporal.workflows.chat_workflow import ChatWorkflow
from tests.integration.conftest import chat_result, embed_result

pytestmark = pytest.mark.integration


async def _make_agent(client, name: str = "A") -> tuple[str, str]:
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (
        await client.post(f"/api/projects/{pid}/agents", json={"name": name})
    ).json()["id"]
    return pid, aid


async def _make_session(client, agent_id: str) -> str:
    r = await client.post(f"/api/agents/{agent_id}/sessions")
    return r.json()["id"]


async def _share(client, agent_id: str, daily_cap: int | None = None) -> str:
    payload = {"daily_message_cap": daily_cap} if daily_cap is not None else {}
    r = await client.post(f"/api/agents/{agent_id}/share", json=payload)
    assert r.status_code == 200
    return r.json()["share_slug"]


async def _make_public_session(client, slug: str) -> str:
    r = await client.post(f"/api/public/agents/{slug}/sessions")
    return r.json()["id"]


# ── Happy path: admin chat ────────────────────────────────────────────────


async def test_admin_chat_runs_real_workflow_end_to_end(integration_client):
    """The whole pipeline — keyword extraction, embedding, vector search,
    hybrid rerank, answer generation, persistence — runs for real, on a real
    Temporal server, with only the LLM calls scripted."""
    _, aid = await _make_agent(integration_client)
    sid = await _make_session(integration_client, aid)

    r = await integration_client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "What's the invoice total?", "session_id": sid},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "The total is $500."
    assert body["keywords"] == ["invoice", "total"]
    assert len(body["retrieved_chunks"]) == 1
    assert body["retrieved_chunks"][0]["filename"] == "invoice.txt"
    assert [s["name"] for s in body["tool_steps"]] == [
        "Extract Keywords",
        "Vector Search",
        "BM25 + Hybrid Rank",
        "Build Context",
        "Generate Answer",
    ]

    # persist_messages activity really ran against the real DB
    messages = (await integration_client.get(f"/api/sessions/{sid}/messages")).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "What's the invoice total?"
    assert messages[1]["content"] == "The total is $500."

    sessions = (await integration_client.get(f"/api/agents/{aid}/sessions")).json()
    assert sessions[0]["title"] == "What's the invoice total?"


async def test_chat_with_no_retrieved_chunks_still_answers(
    integration_client, chroma_mock
):
    """Zero vector-search hits must not crash the pipeline — hybrid_rank,
    context assembly, and answer generation all need to handle it."""
    chroma_mock["chunks"] = []
    _, aid = await _make_agent(integration_client)
    sid = await _make_session(integration_client, aid)

    r = await integration_client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "What's the invoice total?", "session_id": sid},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["retrieved_chunks"] == []
    assert body["answer"] == "The total is $500."
    rank_step = next(s for s in body["tool_steps"] if s["name"] == "BM25 + Hybrid Rank")
    assert rank_step["output_summary"] == "Top score: no results"


# ── Happy path: public share-link chat ───────────────────────────────────


async def test_public_chat_runs_real_workflow_and_hides_pipeline_metadata(
    integration_client,
):
    """Regression test for the metadata-leak fix: the public route must run
    the same real pipeline but return only `answer` — never retrieved_chunks
    (filenames/content) or tool_steps (internal pipeline detail)."""
    _, aid = await _make_agent(integration_client)
    slug = await _share(integration_client, aid)
    sid = await _make_public_session(integration_client, slug)

    r = await integration_client.post(
        f"/api/public/agents/{slug}/chat",
        json={"question": "What's the invoice total?", "session_id": sid},
    )

    assert r.status_code == 200
    assert r.json() == {"answer": "The total is $500."}

    messages = (
        await integration_client.get(
            f"/api/public/agents/{slug}/sessions/{sid}/messages"
        )
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "The total is $500."


async def test_admin_route_rejects_visitor_owned_session(client):
    """A visitor-scoped session created through the public flow must never
    be usable on the authenticated admin chat route, even for the same
    agent. Uses the real DB/session state end-to-end rather than a
    hand-constructed session row."""
    _, aid = await _make_agent(client)
    slug = await _share(client, aid)
    visitor_sid = await _make_public_session(client, slug)

    r = await client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "Hello?", "session_id": visitor_sid},
    )
    assert r.status_code == 404


# ── LLM failure modes ─────────────────────────────────────────────────────


async def test_admin_chat_auth_error_returns_401_and_does_not_persist(
    integration_client, chat_provider
):
    """A non-retryable AUTH_ERROR from the very first LLM call (keyword
    extraction) must short-circuit immediately — no retries, and nothing
    persisted, since the pipeline never reaches persist_messages."""
    chat_provider.responses = [ProviderAuthError("invalid API key")]
    _, aid = await _make_agent(integration_client)
    sid = await _make_session(integration_client, aid)

    r = await integration_client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "What's the invoice total?", "session_id": sid},
    )

    assert r.status_code == 401
    assert (await integration_client.get(f"/api/sessions/{sid}/messages")).json() == []


async def test_admin_chat_retries_transient_failure_then_succeeds(
    integration_client, chat_provider
):
    """generate_answer fails twice with a retryable error, then succeeds on
    the 3rd attempt (within the 4-attempt policy) — exercises Temporal's
    real retry/backoff via the time-skipping test server, not a mock."""
    chat_provider.responses = [
        chat_result('["invoice", "total"]'),  # keyword extraction succeeds
        ProviderServiceError("rate limited", reason="rate_limit"),
        ProviderServiceError("rate limited", reason="rate_limit"),
        chat_result("The total is $500."),  # 3rd attempt succeeds
    ]
    _, aid = await _make_agent(integration_client)
    sid = await _make_session(integration_client, aid)

    r = await integration_client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "What's the invoice total?", "session_id": sid},
    )

    assert r.status_code == 200
    assert r.json()["answer"] == "The total is $500."
    assert chat_provider.responses == []  # every scripted call was consumed


async def test_admin_chat_rate_limit_exhausted_returns_429_and_does_not_persist(
    integration_client, chat_provider
):
    """generate_answer fails on all 4 attempts allowed by the retry policy —
    must surface as 429 once retries are exhausted, with nothing persisted."""
    chat_provider.responses = [
        chat_result('["invoice", "total"]'),
        ProviderServiceError("rate limited", reason="rate_limit"),
        ProviderServiceError("rate limited", reason="rate_limit"),
        ProviderServiceError("rate limited", reason="rate_limit"),
        ProviderServiceError("rate limited", reason="rate_limit"),
    ]
    _, aid = await _make_agent(integration_client)
    sid = await _make_session(integration_client, aid)

    r = await integration_client.post(
        f"/api/agents/{aid}/chat",
        json={"question": "What's the invoice total?", "session_id": sid},
    )

    assert r.status_code == 429
    assert (await integration_client.get(f"/api/sessions/{sid}/messages")).json() == []


async def test_get_agent_config_not_found_is_non_retryable(
    temporal_env, chat_worker, task_queue
):
    """Workflow-level check (bypassing the HTTP route, which already
    pre-checks agent existence and would never reach this branch in
    practice): a missing agent must fail get_agent_config immediately,
    without burning any of the infra retry policy's 10 attempts."""
    with pytest.raises(WorkflowFailureError) as exc_info:
        await temporal_env.client.execute_workflow(
            ChatWorkflow.run,
            args=["00000000-0000-0000-0000-000000000000", "s1", "Hello?"],
            id="test-not-found",
            task_queue=task_queue,
        )

    cause = exc_info.value.cause
    assert isinstance(cause, ActivityError)
    assert isinstance(cause.cause, ApplicationError)
    assert cause.cause.type == "NOT_FOUND"
    assert cause.cause.non_retryable is True


# ── Public share-link daily cap ───────────────────────────────────────────


async def test_public_daily_cap_enforced_and_released_across_real_calls(
    integration_client, chat_provider, embedding_provider
):
    """A cap of 2: two real end-to-end sends succeed, a 3rd is rejected —
    exercising reserve_daily_share_slot/release_daily_share_slot across
    genuine workflow executions rather than a mocked-out workflow."""
    chat_provider.responses = [
        chat_result('["q1"]'),
        chat_result("Answer one."),
        chat_result('["q2"]'),
        chat_result("Answer two."),
    ]
    embedding_provider.responses = [embed_result(), embed_result()]

    _, aid = await _make_agent(integration_client)
    slug = await _share(integration_client, aid, daily_cap=2)
    sid = await _make_public_session(integration_client, slug)

    r1 = await integration_client.post(
        f"/api/public/agents/{slug}/chat",
        json={"question": "Q1?", "session_id": sid},
    )
    r2 = await integration_client.post(
        f"/api/public/agents/{slug}/chat",
        json={"question": "Q2?", "session_id": sid},
    )
    r3 = await integration_client.post(
        f"/api/public/agents/{slug}/chat",
        json={"question": "Q3?", "session_id": sid},
    )

    assert r1.status_code == 200
    assert r1.json()["answer"] == "Answer one."
    assert r2.status_code == 200
    assert r2.json()["answer"] == "Answer two."
    assert r3.status_code == 429

    messages = (
        await integration_client.get(
            f"/api/public/agents/{slug}/sessions/{sid}/messages"
        )
    ).json()
    assert len([m for m in messages if m["role"] == "assistant"]) == 2
