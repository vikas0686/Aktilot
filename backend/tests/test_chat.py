from unittest.mock import AsyncMock, MagicMock, patch

from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError


async def _make_agent(client) -> tuple[str, str]:
    """Returns (project_id, agent_id)."""
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    aid = (await client.post(f"/api/projects/{pid}/agents", json={"name": "A"})).json()[
        "id"
    ]
    return pid, aid


# Minimal workflow result dict that ChatWorkflow.run returns
_FAKE_RESULT = {
    "answer": "The answer is 42.",
    "keywords": ["answer"],
    "chunks": [],
    "steps": [],
}


def _mock_temporal(result: dict = _FAKE_RESULT):
    """Context manager that patches get_temporal_client with a mock Temporal client."""
    mock_tc = MagicMock()
    mock_tc.execute_workflow = AsyncMock(return_value=result)
    return patch(
        "api.routes.agent_chat.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ), mock_tc


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
    patcher, _ = _mock_temporal()
    with patcher:
        r = await client.post(
            f"/api/agents/{aid}/chat", json={"question": "What is 42?"}
        )

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "The answer is 42."
    assert isinstance(body["tool_steps"], list)
    assert isinstance(body["retrieved_chunks"], list)
    assert isinstance(body["keywords"], list)


async def test_chat_passes_question_to_workflow(client):
    _, aid = await _make_agent(client)
    patcher, mock_tc = _mock_temporal()
    with patcher:
        await client.post(
            f"/api/agents/{aid}/chat", json={"question": "What is the deadline?"}
        )

    # execute_workflow is called as: execute_workflow(ChatWorkflow.run, args=[agent_id, question], ...)
    call_kwargs = mock_tc.execute_workflow.call_args
    assert call_kwargs.kwargs["args"][1] == "What is the deadline?"


# ── Temporal error → HTTP status propagation ──────────────────────────────────


def _workflow_failure(error_type: str | None) -> WorkflowFailureError:
    """Build the full WorkflowFailureError → ActivityError → ApplicationError chain."""
    app_err = ApplicationError(
        "activity error",
        type=error_type,
        non_retryable=True,
    )
    act_err = ActivityError(
        message="activity failed",
        scheduled_event_id=1,
        started_event_id=2,
        identity="worker",
        activity_type="extract_keywords",
        activity_id="1",
        retry_state=None,
    )
    act_err.__cause__ = app_err
    return WorkflowFailureError(cause=act_err)


async def test_chat_workflow_auth_error_returns_401(client):
    _, aid = await _make_agent(client)
    mock_tc = MagicMock()
    mock_tc.execute_workflow = AsyncMock(side_effect=_workflow_failure("AUTH_ERROR"))
    with patch(
        "api.routes.agent_chat.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        r = await client.post(f"/api/agents/{aid}/chat", json={"question": "test"})
    assert r.status_code == 401


async def test_chat_workflow_rate_limit_returns_429(client):
    _, aid = await _make_agent(client)
    mock_tc = MagicMock()
    mock_tc.execute_workflow = AsyncMock(side_effect=_workflow_failure("RATE_LIMIT"))
    with patch(
        "api.routes.agent_chat.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        r = await client.post(f"/api/agents/{aid}/chat", json={"question": "test"})
    assert r.status_code == 429


async def test_chat_workflow_unrecognized_failure_returns_500(client):
    _, aid = await _make_agent(client)
    mock_tc = MagicMock()
    mock_tc.execute_workflow = AsyncMock(side_effect=_workflow_failure(None))
    with patch(
        "api.routes.agent_chat.get_temporal_client",
        new_callable=AsyncMock,
        return_value=mock_tc,
    ):
        r = await client.post(f"/api/agents/{aid}/chat", json={"question": "test"})
    assert r.status_code == 500
