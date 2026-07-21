"""
GithubSyncWorkflow — durable, individually-retryable GitHub repo ingestion.

Both "full" (first connect) and "refresh" (manual re-sync) runs always clear
this repo's existing chunks and re-pull everything fresh — no incremental
diffing — per the product requirement that "refresh" means delete-and-repull.
`mode` is carried through only for logging/labeling.

Step order and checkpointing (mirrors DocumentWorkflow):
  1. mark_connection_syncing                         — Postgres, cheap, retry freely
  2. fetch_repo_tree                                  — Git Trees API, checkpointed on success
  3. fetch_file_contents                              — Git Blobs API + chunking, reads the tree file
  4. fetch_issues                                     — Issues + comments API, chunked per issue
  5. clear_existing_vectors_for_repo                  — ChromaDB cleanup, retry freely
  6. embed_and_index_github_chunks                     — OpenAI + ChromaDB, expensive:
                                                        retried alone if it fails
  7. mark_connection_synced                           — Postgres, cheap, retry freely

If any step exhausts retries, sync_status is set to "error" with the failure
message before re-raising.
"""

from datetime import timedelta
from typing import Literal

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.github_activities import (
        clear_existing_vectors_for_repo,
        embed_and_index_github_chunks,
        fetch_file_contents,
        fetch_issues,
        fetch_repo_tree,
        mark_connection_error,
        mark_connection_synced,
        mark_connection_syncing,
    )

TASK_QUEUE = "aktilot-queue"

_INFRA_RETRY = RetryPolicy(
    maximum_attempts=10,
    initial_interval=timedelta(milliseconds=500),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
)

_GITHUB_RETRY = RetryPolicy(
    maximum_attempts=6,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    # ApplicationError(non_retryable=True) bypasses this policy at the activity level
)

_OPENAI_RETRY = RetryPolicy(
    maximum_attempts=10,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
)


@workflow.defn
class GithubSyncWorkflow:
    @workflow.run
    async def run(
        self,
        connection_id: str,
        project_id: str,
        installation_id: int,
        repo_full_name: str,
        branch: str,
        mode: Literal["full", "refresh"] = "full",
    ) -> None:
        await workflow.execute_activity(
            mark_connection_syncing,
            args=[connection_id],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=_INFRA_RETRY,
        )

        try:
            tree_result: dict = await workflow.execute_activity(
                fetch_repo_tree,
                args=[
                    connection_id,
                    project_id,
                    installation_id,
                    repo_full_name,
                    branch,
                ],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_GITHUB_RETRY,
            )
            tree_count: int = tree_result["count"]
            tree_truncated: bool = tree_result["truncated"]

            # Chunks are written to temp files on disk — not passed through Temporal
            # history — so large repos never hit the 4 MB payload limit.
            await workflow.execute_activity(
                fetch_file_contents,
                args=[connection_id, project_id, installation_id, repo_full_name],
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=_GITHUB_RETRY,
            )

            issue_count: int = await workflow.execute_activity(
                fetch_issues,
                args=[connection_id, project_id, installation_id, repo_full_name],
                start_to_close_timeout=timedelta(minutes=15),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=_GITHUB_RETRY,
            )

            # Idempotent — safe to run even on a first-ever "full" sync.
            await workflow.execute_activity(
                clear_existing_vectors_for_repo,
                args=[project_id, connection_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_INFRA_RETRY,
            )

            # Reads chunks from the temp files — retried independently, fetch steps not re-run
            chunk_count: int = await workflow.execute_activity(
                embed_and_index_github_chunks,
                args=[connection_id, project_id, repo_full_name],
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=_OPENAI_RETRY,
            )

            await workflow.execute_activity(
                mark_connection_synced,
                args=[
                    connection_id,
                    tree_count,
                    issue_count,
                    chunk_count,
                    tree_truncated,
                ],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=_INFRA_RETRY,
            )

        except Exception as exc:
            # Best-effort status update — keeps the UI consistent
            await workflow.execute_activity(
                mark_connection_error,
                args=[connection_id, str(exc)],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=_INFRA_RETRY,
            )
            raise
