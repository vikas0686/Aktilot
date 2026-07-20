"""
Full-stack integration tests for the document ingestion pipeline.

Like test_chat_workflow_integration.py, these run the REAL DocumentWorkflow
on a REAL ephemeral Temporal server through a REAL Worker running the REAL
activities — only the embedding provider and ChromaDB calls are mocked (see
tests/integration/conftest.py). Before this file, document_activities.py and
document_workflow.py had zero test coverage at all: test_files.py mocks the
whole workflow away via start_workflow, so the read -> chunk -> embed -> index
-> status pipeline never actually ran in any test.

The upload route uses start_workflow (fire-and-forget), not execute_workflow,
so these tests explicitly await the workflow handle to observe completion.
"""

import io
import uuid

import pytest
from temporalio.client import WorkflowFailureError

from db.models.file import File
from db.models.project import Project
from services.llm.base import ProviderAuthError
from temporal.workflows.document_workflow import DocumentWorkflow
from tests.integration.conftest import ScriptedProvider, embed_result

pytestmark = pytest.mark.integration


async def _create_project(client) -> str:
    return (await client.post("/api/projects", json={"name": "P"})).json()["id"]


async def _upload(
    client, project_id: str, content: bytes, filename: str = "doc.txt"
) -> str:
    r = await client.post(
        f"/api/projects/{project_id}/files/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _get_file(client, project_id: str, file_id: str) -> dict:
    files = (await client.get(f"/api/projects/{project_id}/files")).json()
    return next(f for f in files if f["id"] == file_id)


# ── Happy path ─────────────────────────────────────────────────────────────


async def test_document_upload_runs_real_workflow_end_to_end(
    document_integration_client, temporal_env, chroma_document_mock
):
    pid = await _create_project(document_integration_client)
    content = b"hello world " * 300  # long enough to split into multiple chunks
    fid = await _upload(document_integration_client, pid, content)

    await temporal_env.client.get_workflow_handle(f"doc-{fid}").result()

    record = await _get_file(document_integration_client, pid, fid)
    assert record["chunk_status"] == "chunked"
    assert record["chunk_count"] > 1

    # embed_and_index_chunks really ran and really called add_chunks
    assert len(chroma_document_mock["added"]) == 1
    added_project_id, chunk_dicts, embeddings = chroma_document_mock["added"][0]
    assert added_project_id == pid
    assert len(chunk_dicts) == record["chunk_count"]
    assert len(embeddings) == record["chunk_count"]
    assert all(c["metadata"]["filename"] == "doc.txt" for c in chunk_dicts)
    assert [c["metadata"]["chunk_index"] for c in chunk_dicts] == list(
        range(record["chunk_count"])
    )


async def test_document_workflow_cleans_up_temp_chunks_file_after_success(
    document_integration_client, temporal_env, isolated_upload_dir
):
    from temporal.activities.document_activities import _chunks_path

    pid = await _create_project(document_integration_client)
    fid = await _upload(document_integration_client, pid, b"short content")

    await temporal_env.client.get_workflow_handle(f"doc-{fid}").result()

    assert not _chunks_path(pid, fid).exists()


async def test_document_workflow_small_file_produces_one_chunk(
    document_integration_client, temporal_env
):
    pid = await _create_project(document_integration_client)
    fid = await _upload(document_integration_client, pid, b"a tiny document")

    await temporal_env.client.get_workflow_handle(f"doc-{fid}").result()

    record = await _get_file(document_integration_client, pid, fid)
    assert record["chunk_status"] == "chunked"
    assert record["chunk_count"] == 1


# ── Failure modes ────────────────────────────────────────────────────────────


async def test_document_workflow_missing_file_on_disk_sets_error_status(
    document_worker, temporal_env, task_queue, db_session, tmp_path
):
    """A File row whose file was never actually written to disk (or was
    removed) must fail non-retryably and leave the record's status as
    'error' rather than stuck on 'pending'/'chunking' forever."""
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()
    project = Project(id=project_id, name="P")
    # Under pytest's per-test tmp_path — guaranteed not to exist since we
    # never write to it, without relying on an assumption about the root
    # filesystem layout.
    missing_path = tmp_path / "ghost.txt"
    file_record = File(
        id=file_id,
        project_id=project_id,
        filename="ghost.txt",
        filepath=str(missing_path),
        size=0,
        chunk_status="pending",
    )
    db_session.add(project)
    db_session.add(file_record)
    await db_session.commit()

    with pytest.raises(WorkflowFailureError):
        await temporal_env.client.execute_workflow(
            DocumentWorkflow.run,
            args=[str(file_id), str(project_id)],
            id=f"doc-{file_id}",
            task_queue=task_queue,
        )

    # The activities' patched AsyncSessionFactory writes through a different
    # session bound to the same engine — refresh this one to see it.
    await db_session.refresh(file_record)
    assert file_record.chunk_status == "error"


async def test_document_workflow_auth_error_sets_error_status(
    document_integration_client,
    temporal_env,
    document_embedding_provider: ScriptedProvider,
):
    document_embedding_provider.responses = [ProviderAuthError("invalid API key")]

    pid = await _create_project(document_integration_client)
    fid = await _upload(document_integration_client, pid, b"some content")

    with pytest.raises(WorkflowFailureError):
        await temporal_env.client.get_workflow_handle(f"doc-{fid}").result()

    record = await _get_file(document_integration_client, pid, fid)
    assert record["chunk_status"] == "error"


async def test_document_workflow_retries_transient_failure_then_succeeds(
    document_integration_client,
    temporal_env,
    document_embedding_provider: ScriptedProvider,
):
    """The embed step fails twice with a plain (retryable-by-default,
    non-ApplicationError) exception, then succeeds on the 3rd attempt —
    exercising the workflow's real OpenAI retry policy end to end."""
    document_embedding_provider.responses = [
        RuntimeError("transient network error"),
        RuntimeError("transient network error"),
        embed_result(),
    ]

    pid = await _create_project(document_integration_client)
    fid = await _upload(document_integration_client, pid, b"some content")

    await temporal_env.client.get_workflow_handle(f"doc-{fid}").result()

    record = await _get_file(document_integration_client, pid, fid)
    assert record["chunk_status"] == "chunked"
    assert document_embedding_provider.responses == []  # every scripted call consumed
