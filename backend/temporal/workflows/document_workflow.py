"""
DocumentWorkflow — durable, individually-retryable document ingestion pipeline.

Step order and checkpointing:
  1. update_file_status("chunking")        — Postgres, cheap, retry freely
  2. read_and_split_file(file_id)          — disk + CPU, checkpointed on success
  3. clear_existing_vectors(...)           — ChromaDB cleanup, retry freely
  4. embed_and_index_chunks(...)           — OpenAI + ChromaDB, expensive:
                                             retried alone if it fails — steps 1-3 are NOT re-run
  5. update_file_status("chunked", count) — Postgres, cheap, retry freely

If any step exhausts retries, status is set to "error" before re-raising.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.document_activities import (
        clear_existing_vectors,
        embed_and_index_chunks,
        read_and_split_file,
        update_file_status,
    )

TASK_QUEUE = "aktilot-queue"

_INFRA_RETRY = RetryPolicy(
    maximum_attempts=10,
    initial_interval=timedelta(milliseconds=500),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
)

_OPENAI_RETRY = RetryPolicy(
    maximum_attempts=10,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    # ApplicationError(non_retryable=True) bypasses this policy at the activity level
)


@workflow.defn
class DocumentWorkflow:
    @workflow.run
    async def run(self, file_id: str, project_id: str) -> None:
        await workflow.execute_activity(
            update_file_status,
            args=[file_id, "chunking"],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=_INFRA_RETRY,
        )

        try:
            # Chunks are written to a temp file on disk — not passed through Temporal
            # history — so large documents never hit the 4 MB payload limit.
            result: dict = await workflow.execute_activity(
                read_and_split_file,
                args=[file_id, project_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=1),
                ),
            )
            _ = result[
                "chunk_count"
            ]  # small metadata, actual count comes from embed step

            await workflow.execute_activity(
                clear_existing_vectors,
                args=[project_id, file_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_INFRA_RETRY,
            )

            # Reads chunks from the temp file — retried independently, file read not re-run
            chunk_count: int = await workflow.execute_activity(
                embed_and_index_chunks,
                args=[project_id, file_id],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=_OPENAI_RETRY,
            )

            await workflow.execute_activity(
                update_file_status,
                args=[file_id, "chunked", chunk_count],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=_INFRA_RETRY,
            )

        except Exception:
            # Best-effort status update — keeps the UI consistent
            await workflow.execute_activity(
                update_file_status,
                args=[file_id, "error"],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=_INFRA_RETRY,
            )
            raise
