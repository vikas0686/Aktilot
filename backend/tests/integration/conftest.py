"""
Fixtures for full-stack chat pipeline integration tests.

Unlike tests/test_chat.py (stubs the whole Temporal workflow) and
tests/test_chat_activities.py (calls each activity function directly, in
isolation), the tests under this package run the REAL ChatWorkflow on a REAL
(ephemeral, in-process) Temporal server, through a REAL Worker executing the
REAL activities in temporal/activities/chat_activities.py — orchestration,
retry policies, and Postgres/SQLite persistence all execute for real.

Exactly two things are mocked, both at the same seams tests/test_chat_activities.py
already uses:
  - get_chat_provider / get_embedding_provider — no real OpenAI calls.
  - chroma_search — ChromaDB itself is globally replaced with a MagicMock in
    tests/conftest.py, which can't serve realistic vector search results, so
    there's nothing genuine to integrate with there.

Everything else — the HTTP route, Temporal's orchestration and retry
policies, and the database — is real. `AsyncSessionFactory` is patched only
to point activities at the same in-memory SQLite engine the `client` fixture
already uses, not to fake persistence.
"""

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from services.llm.base import ChatResult, EmbedResult
from temporal.activities import chat_activities, document_activities
from temporal.workflows.chat_workflow import ChatWorkflow
from temporal.workflows.document_workflow import DocumentWorkflow

pytestmark = pytest.mark.integration

FAKE_VECTOR = [0.1] * 10

FAKE_CHUNK = {
    "id": "c1",
    "content": "The invoice total is $500, due January 31.",
    "metadata": {"filename": "invoice.txt", "chunk_index": 0},
    "distance": 0.1,
}


def chat_result(content: str, prompt: int = 10, completion: int = 5) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        finish_reason="stop",
    )


def embed_result(vector: list[float] | None = None, tokens: int = 10) -> EmbedResult:
    return EmbedResult(embeddings=[vector or FAKE_VECTOR], total_tokens=tokens)


@dataclass
class ScriptedProvider:
    """A fake ChatProvider/EmbeddingProvider whose calls are scripted up front.

    `responses` is consumed strictly in call order. An item that is an
    Exception (instance or class) is raised instead of returned — this lets a
    test script "fail N times then succeed" to exercise Temporal's real retry
    policy, or "fail once, non-retryably" to exercise the AUTH_ERROR path.
    """

    responses: list[Any]
    calls: list[Any]

    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls = []

    async def generate(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        return self._next()

    async def embed(self, **kwargs) -> EmbedResult:
        self.calls.append(kwargs)
        result = self._next()
        # A scripted single-vector EmbedResult is a template for a successful
        # call, not literally "one embedding regardless of input" — broadcast
        # it across all requested texts (embed_query always asks for exactly
        # one, so this is a no-op there; embed_and_index_chunks asks for a
        # whole batch at once and needs one vector per text).
        if isinstance(result, EmbedResult) and len(result.embeddings) == 1:
            texts = kwargs.get("texts", [])
            if len(texts) > 1:
                return EmbedResult(
                    embeddings=result.embeddings * len(texts),
                    total_tokens=result.total_tokens,
                )
        return result

    def _next(self):
        if not self.responses:
            raise AssertionError("ScriptedProvider ran out of scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item()
        return item


@pytest_asyncio.fixture
async def temporal_env() -> AsyncGenerator[WorkflowEnvironment, None]:
    """A real, ephemeral, time-skipping Temporal server for this test only.

    Time-skipping means retry backoffs (e.g. the 2s/4s/8s OpenAI retry
    policy) resolve near-instantly instead of costing real wall-clock time,
    while still exercising Temporal's actual retry/backoff logic.
    """
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        yield env
    finally:
        await env.shutdown()


@pytest.fixture
def task_queue() -> str:
    # Unique per test so parallel/reordered test runs never share a queue.
    return f"test-chat-queue-{uuid.uuid4()}"


@pytest.fixture
def chat_provider(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    """Default: one scripted call (keyword extraction) + one (answer
    generation). Override by reassigning `.responses` before the request that
    triggers the workflow, or by depending on this fixture and mutating it."""
    provider = ScriptedProvider(
        [chat_result('["invoice", "total"]'), chat_result("The total is $500.")]
    )
    monkeypatch.setattr(
        "temporal.activities.chat_activities.get_chat_provider",
        lambda *a, **kw: provider,
    )
    return provider


@pytest.fixture
def embedding_provider(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    provider = ScriptedProvider([embed_result()])
    monkeypatch.setattr(
        "temporal.activities.chat_activities.get_embedding_provider",
        lambda *a, **kw: provider,
    )
    return provider


@pytest.fixture
def chroma_mock(monkeypatch: pytest.MonkeyPatch):
    """Default: one matching chunk. Tests wanting empty retrieval pass
    `chunks=[]` via `configure_chroma`."""
    state = {"chunks": [FAKE_CHUNK]}

    def _search(project_id, query_vector, k=20):
        return state["chunks"]

    monkeypatch.setattr("temporal.activities.chat_activities.chroma_search", _search)
    return state


@pytest_asyncio.fixture
async def chat_worker(
    temporal_env: WorkflowEnvironment,
    engine,
    task_queue: str,
    chat_provider: ScriptedProvider,
    embedding_provider: ScriptedProvider,
    chroma_mock: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[Worker, None]:
    """A real Temporal Worker running the real ChatWorkflow + activities,
    with activities' DB access repointed at the test's in-memory engine."""
    test_sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(
        "temporal.activities.chat_activities.AsyncSessionFactory", test_sessionmaker
    )

    worker = Worker(
        temporal_env.client,
        task_queue=task_queue,
        workflows=[ChatWorkflow],
        activities=[
            chat_activities.get_agent_config,
            chat_activities.extract_keywords,
            chat_activities.embed_query,
            chat_activities.search_vectors,
            chat_activities.hybrid_rank,
            chat_activities.generate_answer,
            chat_activities.persist_messages,
        ],
    )
    async with worker:
        yield worker


@pytest_asyncio.fixture
async def integration_client(
    client,
    temporal_env: WorkflowEnvironment,
    task_queue: str,
    chat_worker: Worker,
    monkeypatch: pytest.MonkeyPatch,
):
    """The shared HTTP `client` fixture, wired so its chat routes drive the
    REAL ChatWorkflow on the ephemeral test server instead of a stub."""

    async def _fake_get_client() -> Client:
        return temporal_env.client

    monkeypatch.setattr("api.routes.agent_chat.get_temporal_client", _fake_get_client)
    monkeypatch.setattr("api.routes.agent_chat.TASK_QUEUE", task_queue)
    return client


# ── DocumentWorkflow fixtures ──────────────────────────────────────────────────


@pytest.fixture
def isolated_upload_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Redirects both the upload route's on-disk file writes and
    document_activities' chunks temp file into tmp_path — `config.settings` is
    a shared singleton, so patching the attribute here affects every module
    that reads `settings.upload_dir`, not just one of them."""
    monkeypatch.setattr("config.settings.upload_dir", tmp_path)
    return tmp_path


@pytest.fixture
def document_embedding_provider(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    """document_activities.py imports get_embedding_provider independently of
    chat_activities.py — a separate module-level name needs its own patch."""
    provider = ScriptedProvider([embed_result()])
    monkeypatch.setattr(
        "temporal.activities.document_activities.get_embedding_provider",
        lambda *a, **kw: provider,
    )
    return provider


@pytest.fixture
def chroma_document_mock(monkeypatch: pytest.MonkeyPatch):
    """Records add_chunks/chroma_delete_file calls instead of touching the
    globally-mocked chromadb module, which can't serve realistic behavior."""
    state = {"added": [], "deleted": []}

    def _add_chunks(project_id, chunks, embeddings):
        state["added"].append((project_id, chunks, embeddings))

    def _delete_file(project_id, file_id):
        state["deleted"].append((project_id, file_id))

    monkeypatch.setattr(
        "temporal.activities.document_activities.add_chunks", _add_chunks
    )
    monkeypatch.setattr(
        "temporal.activities.document_activities.chroma_delete_file", _delete_file
    )
    return state


@pytest_asyncio.fixture
async def document_worker(
    temporal_env: WorkflowEnvironment,
    engine,
    task_queue: str,
    document_embedding_provider: ScriptedProvider,
    chroma_document_mock: dict,
    isolated_upload_dir,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[Worker, None]:
    """A real Temporal Worker running the real DocumentWorkflow + activities,
    with activities' DB access repointed at the test's in-memory engine."""
    test_sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(
        "temporal.activities.document_activities.AsyncSessionFactory", test_sessionmaker
    )

    worker = Worker(
        temporal_env.client,
        task_queue=task_queue,
        workflows=[DocumentWorkflow],
        activities=[
            document_activities.update_file_status,
            document_activities.read_and_split_file,
            document_activities.clear_existing_vectors,
            document_activities.embed_and_index_chunks,
        ],
    )
    async with worker:
        yield worker


@pytest_asyncio.fixture
async def document_integration_client(
    client,
    temporal_env: WorkflowEnvironment,
    task_queue: str,
    document_worker: Worker,
    monkeypatch: pytest.MonkeyPatch,
):
    """The shared HTTP `client` fixture, wired so uploads dispatch the REAL
    DocumentWorkflow on the ephemeral test server instead of a stub. Note the
    route uses start_workflow (fire-and-forget), not execute_workflow — tests
    must separately await completion via a workflow handle."""

    async def _fake_get_client() -> Client:
        return temporal_env.client

    monkeypatch.setattr(
        "api.routes.project_files.get_temporal_client", _fake_get_client
    )
    monkeypatch.setattr("api.routes.project_files.TASK_QUEUE", task_queue)
    return client
