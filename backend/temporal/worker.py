"""
Temporal worker — run this as a separate process alongside FastAPI.

    python -m temporal.worker

Registers DocumentWorkflow and ChatWorkflow — and all their activities — on
the aktilot-queue task queue.
"""

import asyncio

from temporalio.client import Client
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig
from temporalio.worker import Worker

from config import settings
from observability.otel import configure_otel
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
from temporal.interceptors import MetricsInterceptor
from temporal.workflows.chat_workflow import TASK_QUEUE, ChatWorkflow
from temporal.workflows.document_workflow import DocumentWorkflow


def _seed_gauge_cache() -> None:
    """Populate ObservableGauge caches from ChromaDB so values survive restarts."""
    try:
        import chromadb

        import observability.metrics as m
        from config import settings as _s

        client = chromadb.PersistentClient(path=str(_s.chroma_dir))
        for col in client.list_collections():
            try:
                count = col.count()
                project_id = col.name.removeprefix("project_")
                m.update_vectordb_size(project_id, col.name, count)
            except Exception:
                pass
    except Exception:
        pass  # best-effort; never block worker startup


async def main() -> None:
    configure_otel("aktilot-worker")
    _seed_gauge_cache()

    # Temporal SDK built-in metrics (workflow latency, activity execution time,
    # queue scheduling delay, slots available) pushed to the same OTel collector.
    runtime = Runtime(
        telemetry=TelemetryConfig(
            metrics=OpenTelemetryConfig(
                url=settings.otel_endpoint,
                http=False,  # port 4317 is gRPC; http=True would need port 4318
            )
        )
    )

    client = await Client.connect(
        settings.temporal_address,
        interceptors=[TracingInterceptor()],
        runtime=runtime,
    )
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
        interceptors=[TracingInterceptor(), MetricsInterceptor()],
    )
    print(f"[worker] connected to {settings.temporal_address}, queue={TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
