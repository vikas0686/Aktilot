# Observability

Aktilot ships with a full observability stack out of the box. Every component of the RAG pipeline — from document ingestion to LLM calls to ChromaDB queries — is instrumented with OpenTelemetry and visualised in Grafana.

---

## Stack

```
Aktilot (API + Worker)
    │
    │  OTLP/gRPC
    ▼
OpenTelemetry Collector
    ├──► Prometheus  (metrics)
    └──► Grafana Tempo  (traces)
         │
         ▼
       Grafana  (dashboards)
```

| Service | Local URL | Purpose |
|---|---|---|
| Grafana | http://localhost:3002 | Dashboards (metrics + traces) |
| Prometheus | http://localhost:9090 | Metrics store + query engine |
| Grafana Tempo | http://localhost:3200 | Distributed trace storage |
| OTEL Collector | http://localhost:8889/metrics | Raw metrics scrape endpoint |
| Temporal UI | http://localhost:8233 | Workflow execution history |

Default Grafana login: **admin / admin**

---

## Dashboards

### 1. RAG Pipeline Overview
**URL:** http://localhost:3002/d/rag-overview

Your first stop. Answers "is the system healthy right now?"

- LLM response latency (generate_answer vs keyword_extract)
- Total chats and LLM success rate
- Average retrieval top-1 score — below 0.4 means retrieval is not finding relevant content
- Activity latency breakdown barchart — shows which pipeline step is the bottleneck
- Chat request volume over time
- Document ingestion embedding latency

---

### 2. Retrieval Quality
**URL:** http://localhost:3002/d/retrieval-quality

Open this when answers feel irrelevant or miss content from uploaded documents.

- **Reranker score over time** — top-1 score is the primary quality signal
- **Avg docs returned** — low value means the collection is too sparse
- **Reranker discard ratio** — expected ~0.7 for k=20 → top_k=6
- **Retrieval score by type** — hybrid vs vector vs BM25; if hybrid < vector, BM25 is hurting the blend
- **Top-K requested vs returned** — gap means collection too sparse for the query
- **Retrieval latency breakdown** — ChromaDB, BM25, hybrid, and reranker stages

---

### 3. Prompt Intelligence
**URL:** http://localhost:3002/d/prompt-intelligence

Open this when token costs spike or you hit context window errors.

- **Prompt token composition** — stacked chart of context / system prompt / user question tokens per query. Rising context = chunks too large or top_k too high. Rising system = prompt template bloat (costs money on every query)
- **Context tokens by project** — identifies which project's chunks are growing
- **Chunks included vs top-K requested** — gap means the context builder hit the token limit and silently dropped chunks

---

### 4. LLM Performance
**URL:** http://localhost:3002/d/llm-performance

Open this when LLM calls feel slow or answers are being cut off.

- **Response latency by purpose** — generate_answer and keyword_extract side by side
- **Finish reason distribution** — `finish_reason=length` means max_tokens was hit and the answer was truncated
- **LLM requests by purpose** — keyword_extract should track 1:1 with generate; divergence means a workflow step is silently failing

---

### 5. Vector DB Health
**URL:** http://localhost:3002/d/vectordb-health

Open this after uploading documents or when retrieval quality degrades over time.

- **Collection size over time** — confirms documents were actually indexed; jumps = bulk uploads
- **Total queries by collection** — identifies hot collections
- **Search latency** — persistent increase = ChromaDB index fragmentation or memory pressure
- **Insert latency** — spikes during ingestion = disk I/O or memory pressure

---

### 6. Token & Cost Intelligence
**URL:** http://localhost:3002/d/token-cost

Open this at end of month or before scaling to production.

- **Cumulative input tokens by model** — primary LLM cost driver
- **Cumulative output tokens by purpose** — generate_answer vs keyword_extract cost split
- **Embedding tokens by call site** — ingestion (bursty, spikes on upload) vs query (steady growth with usage)
- **Input / output token ratio** — rising ratio means answers getting longer; sustained rise may indicate prompt drift

---

### 7. Temporal Workflows
**URL:** http://localhost:3002/d/temporal-workflows

Open this when workflows are slow, failing, or backing up.

- **Total activities executed** — 7 per ChatWorkflow, 4 per DocumentWorkflow
- **Activity retries** — non-zero means a dependency was flaky (OpenAI, ChromaDB, Postgres)
- **Activity failures** — terminal failures after all retries exhausted; each one failed a user-visible workflow
- **Activity execution latency by type** — core panel; generate_answer dominates (LLM call)
- **Worker task slots available vs used** — slots dropping to 0 = worker saturated
- **Activity queue delay** — time between Temporal scheduling an activity and the worker picking it up; rising = worker overloaded or crashed
- **Retries by activity** — which specific activity is flaky
- **Workflow cache (sticky execution)** — cache hits mean Temporal is not replaying history from scratch

---

## Traces

Every API request and Temporal workflow activity is traced end to end. Traces are stored in Grafana Tempo and viewable directly in Grafana.

**To explore traces:**
1. Open Grafana → Explore → select **Tempo** datasource
2. Search by service name: `aktilot-api` or `aktilot-worker`
3. Or click any trace ID shown alongside a Grafana panel

Traces link API requests → workflow executions → individual activity spans, so you can follow a single user query from the HTTP endpoint through every pipeline step.

---

## Metrics Reference

All custom metrics use the `rag.*` prefix and are exported via OTLP to the collector. Temporal SDK built-in metrics use the `temporal_*` prefix.

| Prefix | Source | Examples |
|---|---|---|
| `rag_llm_*` | Chat activities | `rag_llm_request_latency_ms`, `rag_llm_requests_total` |
| `rag_embedding_*` | Embedding calls | `rag_embedding_latency_ms`, `rag_embedding_tokens_total` |
| `rag_retrieval_*` | Vector + BM25 search | `rag_retrieval_top_k_returned`, `rag_retrieval_score_avg` |
| `rag_reranker_*` | Hybrid reranking | `rag_reranker_score_top1`, `rag_reranker_latency_ms` |
| `rag_prompt_*` | Prompt assembly | `rag_prompt_tokens_context`, `rag_prompt_chunks_included` |
| `rag_vectordb_*` | ChromaDB operations | `rag_vectordb_collection_size`, `rag_vectordb_search_latency_ms` |
| `rag_tokens_*` | Cost tracking | `rag_tokens_input_total`, `rag_tokens_embedding_total` |
| `rag_workflow_*` | Temporal activities | `rag_workflow_activity_duration_ms`, `rag_workflow_retries_total` |
| `temporal_*` | Temporal SDK | `temporal_activity_execution_latency`, `temporal_worker_task_slots_available` |

Full metric definitions: [`backend/observability/metrics.py`](backend/observability/metrics.py)

---

## Configuration

The observability stack starts automatically with `docker compose up`. No additional setup required.

Relevant files:

| File | Purpose |
|---|---|
| `otel-collector-config.yaml` | OTEL Collector pipeline — receivers, processors, exporters |
| `grafana/provisioning/dashboards/` | Dashboard JSON files — auto-provisioned on startup |
| `grafana/provisioning/datasources/` | Prometheus and Tempo datasource config |
| `backend/observability/otel.py` | OTel SDK bootstrap (traces, metrics, logs) |
| `backend/observability/metrics.py` | All custom metric instruments |
| `backend/temporal/interceptors.py` | Temporal activity metrics interceptor |
| `docker-compose.yml` | Service definitions including `--query.lookback-delta=10m` for Prometheus |
