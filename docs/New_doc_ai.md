Full Temporal Integration Plan

What you have now and why it breaks

┌─────────────────────────────────────────┬───────────────────────────────────────────────────────────────────┐
│                 Current                 │                              Problem                              │
├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ BackgroundTasks.add_task(chunk_file,    │ Server restart → task silently lost, file stays pending forever   │
│ ...)                                    │                                                                   │
├────────────────────────────────────────────────────────────────────────────────┤
│ agent_rag_service.chat() — monolithic   │ OpenAI call 1 succeeds ($), ChromaDB fails → whole thing retries  │
│                                         gain                                   │
├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ No benchmark pipeline                   durability, no parallel evaluation     │
└────────────────────────────────────────────────────────────────────────────────┘

---
New file structure

backend/
temporal/
client.py                     # get_temporal_client() + FastAPI dependency
worker.py                     # entryps + activities
workflows/
document_workflow.py
chat_workflow.py
benchmark_workflow.py
eval_query_workflow.py      # child
activities/
document_activities.py
chat_activities.py
benchmark_activities.py
db/models/
eval_run.py                   # NEW
eval_result.py                # NEW
alembic/versions/
006_create_eval_tables.py     # NEW

---
Phase 0 — Infrastructure

docker-compose.yml additions:
temporal:
image: temporalio/auto-setup:latest
ports: ["7233:7233"]

temporal-ui:
image: temporalio/ui:latest
ports: ["8233:8080"]
environment:
TEMPORAL_ADDRESS: temporal:7233

requirements.txt addition:
temporalio>=1.7

temporal/client.py:
from temporalio.client import Client

_client: Client | None = None

async def get_temporal_client() -> Client:
global _client
if _client is None:
_client = await Client.connect("lo
return _client

temporal/worker.py — runs as a separate pr
asyncio.run(Worker(client, task_queue="akt
workflows=[DocumentWorkflow, ChatWorkflow, BenchmarkWorkflow, EvalQueryWorkflow],
activities=[...all activities...]).run

---
Phase 1 — DocumentWorkflow

Replaces: background_tasks.add_task(chunk_ect_files.py

Activities (temporal/activities/document_activities.py)

update_file_status(file_id, status, chunk_count?)   ← Postgres  retry: 10x, 500ms backoff
read_and_split_file(file_id) → list[str]   3x, skip FileNotFoundError
clear_existing_vectors(project_id, file_id)         ← ChromaDB   retry: 10x
embed_chunks(chunks) → list[list[float]]   10x, exp backoff, skip 401
index_to_chroma(project_id, file_id, chunks, vecs)  ← ChromaDB   retry: 10x

Workflow (temporal/workflows/document_work

@workflow.defn
class DocumentWorkflow:
@workflow.run
async def run(self, file_id: str, proj
await execute_activity(update_file_status, ["chunking"], ...)

        chunks = await execute_activity(          # checkpointed
            read_and_split_file, [file_id]
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maxim
        )

        await execute_activity(clear_existe_id], ...)

        vectors = await execute_activity(         # checkpointed — if this fails mid-batch,
            embed_chunks, [chunks],               # only embed_chunks retries, not read/split
            start_to_close_timeout=timedel
            retry_policy=OPENAI_RETRY,
        )

        await execute_activity(index_to_chhunks, vectors], ...)
        await execute_activity(update_file_status, ["chunked", len(chunks)], ...)

FastAPI change (api/routes/project_files.p

# Remove:
background_tasks.add_task(project_chunk_service.chunk_file, str(record.id), str(project_id))

# Add:
tc = await get_temporal_client()
await tc.start_workflow(
DocumentWorkflow.run,
args=[str(record.id), str(project_id)],
id=f"doc-{record.id}",          # idempotent — safe to re-upload same file
task_queue="aktilot-queue",
)

---
Phase 2 — ChatWorkflow

Replaces: direct await agent_rag_service.cn api/routes/agent_chat.py

Activities (temporal/activities/chat_activ

get_agent_config(agent_id) → dict          ← Postgres    retry: 5x
extract_keywords(question) → list[str]     backoff, skip 401
embed_query(question) → list[float]        ← OpenAI      retry: 4x, exp backoff, skip 401
search_vectors(project_id, vec, kws) → … ←ms backoff
hybrid_rank(raw, kws, top_k) → list
generate_answer(question, ctx, prompt) → str ← OpenAI    retry: 4x, exp backoff, skip 401
persist_messages(agent_id, q, a)           ← Postgres    retry: 10x

Checkpoint map — what gets saved vs what retries

Step 1: extract_keywords  ✓ ($)  ← checkpointed
Step 2: embed_query       ✓ ($)  ← checkpointed
Step 3: search_vectors    ✗      ← ONLY THIS retries, steps 1+2 results reused
Step 3: search_vectors    ✓      ← checkpo
Step 4: hybrid_rank       ✓
Step 5: generate_answer   ✓ ($)  ← checkpo
Step 6: persist_messages  ✓

Retry policies

OPENAI_RETRY = RetryPolicy(
maximum_attempts=4,
initial_interval=timedelta(seconds=2),
backoff_coefficient=2.0,
maximum_interval=timedelta(seconds=60),
non_retryable_error_types=["Authenticaail fast
)

INFRA_RETRY = RetryPolicy(
maximum_attempts=10,
initial_interval=timedelta(milliseconds=500),
backoff_coefficient=1.5,
)

FastAPI change (api/routes/agent_chat.py)

# execute_workflow waits for result — HTTPflow completes
tc = await get_temporal_client()
result = await tc.execute_workflow(
ChatWorkflow.run,
args=[str(agent_id), request.question],
id=f"chat-{uuid4()}",
task_queue="aktilot-queue",
execution_timeout=timedelta(minutes=2)
)

---
Phase 3 — BenchmarkWorkflow

New DB models

EvalRun    id, agent_id, dataset_path, sta
recall_at_k, mrr, avg_latency_ms, created_at, completed_at

EvalResult id, run_id, query, recall_at_k, mrr, latency_ms,
retrieved_chunk_ids (JSON), rel

Dataset format (JSON file you provide)

[
{
"query": "What is the invoice total?",
"relevant_chunk_ids": ["chunk-abc", "c
}
]

Workflow design

BenchmarkWorkflow(agent_id, dataset_path)
│
├── Activity: create_eval_run(agent_id)
├── Activity: load_dataset(path)
│
├── for each test_case (in parallel, max 5 concurrent):
│     └── child EvalQueryWorkflow(run_id
│           ├── reuses ChatWorkflow activities (extract_keywords → … → generate_answer)
│           ├── Activity: score_results(retrieved, relevant) → Recall@K, MRR, latency
│           └── Activity: save_eval_result(run_id, scores)
│
└── Activity: finalize_run(run_id)             → aggregate avg metrics, mark completed

Sub-workflow parallelism

# In BenchmarkWorkflow:
handles = await asyncio.gather(*[
workflow.start_child_workflow(
EvalQueryWorkflow.run,
args=[run_id, agent_id, case],
id=f"eval-{run_id}-{i}",
)
for i, case in enumerate(test_cases)
])
await asyncio.gather(*handles)   # wait fo

New API routes

POST /api/benchmarks          body: {agent_id, dataset_path}  → {run_id}
GET  /api/benchmarks/{run_id}             n with results
GET  /api/benchmarks/{run_id}/results                          → list[EvalResult]

---
Retry policy summary

┌─────────────────────┬────────────┬──────────┐
│      Activity       │ Dependency │   Max retries   │       Skip on       │
├─────────────────────┼────────────┼──────────┤
│ read_and_split_file │ Disk       │ 3    r   │
├─────────────────────┼────────────┼──────────┤
│ embed_chunks        │ OpenAI     │ 10, eror │
├─────────────────────┼────────────┼──────────┤
│ index_to_chroma     │ ChromaDB   │ 10              │ —                   │
├─────────────────────┼────────────┼──────────┤
│ update_file_status  │ Postgres   │ 10       │
├─────────────────────┼────────────┼──────────┤
│ extract_keywords    │ OpenAI     │ 4, exp backoff  │ AuthenticationError │
├─────────────────────┼────────────┼──────────┤
│ embed_query         │ OpenAI     │ 4, exp backoff  │ AuthenticationError │
├─────────────────────┼────────────┼──────────┤
│ search_vectors      │ ChromaDB   │ 10, 500ms       │ —                   │
├─────────────────────┼────────────┼──────────┤
│ hybrid_rank         │ CPU        │ 3        │
├─────────────────────┼────────────┼──────────┤
│ generate_answer     │ OpenAI     │ 4, exp backoff  │ AuthenticationError │
├─────────────────────┼────────────┼──────────┤
│ persist_messages    │ Postgres   │ 10              │ —                   │
└─────────────────────┴────────────┴──────────┘

---
Implementation order

Week 1:  Phase 0 (infrastructure) + Phase 1 (DocumentWorkflow)
→ immediate fix for the silent lo

Week 2:  Phase 2 (ChatWorkflow)
→ individual retries, no wasted L

Week 3:  Phase 3 (BenchmarkWorkflow)
→ evaluation infrastructure