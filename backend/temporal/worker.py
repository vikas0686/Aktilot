"""
Temporal worker — run this as a separate process alongside FastAPI.

    python -m temporal.worker

Registers DocumentWorkflow and all its activities on the aktilot-document-queue task queue.
"""

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from config import settings
from temporal.activities.document_activities import (
    clear_existing_vectors,
    embed_and_index_chunks,
    read_and_split_file,
    update_file_status,
)
from temporal.workflows.document_workflow import DocumentWorkflow, TASK_QUEUE


async def main() -> None:
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DocumentWorkflow],
        activities=[
            update_file_status,
            read_and_split_file,
            clear_existing_vectors,
            embed_and_index_chunks,
        ],
    )
    print(f"[worker] connected to {settings.temporal_address}, queue={TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
