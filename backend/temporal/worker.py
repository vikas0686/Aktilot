"""
Temporal worker — run this as a separate process alongside FastAPI.

    python -m temporal.worker

Registers DocumentWorkflow and ChatWorkflow — and all their activities — on
the aktilot-queue task queue.
"""

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from config import settings
from temporal.activities.chat_activities import (
    embed_query,
    extract_keywords,
    generate_answer,
    get_agent_config,
    hybrid_rank,
    persist_messages,
    search_vectors,
)
from temporal.activities.document_activities import (
    clear_existing_vectors,
    embed_and_index_chunks,
    read_and_split_file,
    update_file_status,
)
from temporal.workflows.chat_workflow import TASK_QUEUE, ChatWorkflow
from temporal.workflows.document_workflow import DocumentWorkflow


async def main() -> None:
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DocumentWorkflow, ChatWorkflow],
        activities=[
            # document activities
            update_file_status,
            read_and_split_file,
            clear_existing_vectors,
            embed_and_index_chunks,
            # chat activities
            get_agent_config,
            extract_keywords,
            embed_query,
            search_vectors,
            hybrid_rank,
            generate_answer,
            persist_messages,
        ],
    )
    print(f"[worker] connected to {settings.temporal_address}, queue={TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
