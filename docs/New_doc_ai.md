# Observable RAG Pipeline: OpenTelemetry + Grafana + Temporal

## Current Stack

- FastAPI + SQLAlchemy backend
- Temporal (DocumentWorkflow, ChatWorkflow with 8 activities)
- ChromaDB vector store, OpenAI for LLM/embeddings
- React frontend, Docker Compose

---

## Architecture

```
FastAPI ──────────────────────────────────────┐
  │ auto: HTTP spans, SQLAlchemy spans         │
  │                                            │
Temporal Worker ──────────────────────────────┤  OTLP/gRPC
  │ auto: workflow + activity spans            ├──────────► OTEL Collector
  │ custom metrics:                            │                │
  │   • rag.retrieval.latency_ms (hist)       │                ├──► Prometheus ──► Grafana
  │   • rag.llm.tokens_total (counter)        │                ├──► Tempo        ──► Grafana
  │   • rag.retrieval.score (hist)            │                └──► Loki         ──► Grafana
  │   • rag.chunks_retrieved (hist)           │
  │   • rag.activity_retries (counter)        │
  │   • doc.chunks_produced (hist)            │
  │   • doc.processing_latency_ms (hist)      │
  └────────────────────────────────────────────┘
```

---

## Phase 1 — Infrastructure (docker-compose additions)

Add 4 new services: **OTEL Collector**, **Prometheus**, **Grafana Tempo**, **Grafana**.

New files to create:

| File | Purpose |
|---|---|
| `otel-collector-config.yaml` | Receives OTLP, exports to Prometheus + Tempo + Loki |
| `prometheus.yml` | Scrapes OTEL Collector's Prometheus exporter |
| `grafana/provisioning/datasources/datasources.yaml` | Wires Prometheus + Tempo into Grafana |
| `grafana/provisioning/dashboards/` | Pre-provisioned dashboard JSONs |

---

## Phase 2 — Python Dependencies

Add to `backend/requirements.txt`:

```
opentelemetry-sdk>=1.25
opentelemetry-exporter-otlp-proto-grpc>=1.25
opentelemetry-instrumentation-fastapi>=0.46b0
opentelemetry-instrumentation-sqlalchemy>=0.46b0
opentelemetry-instrumentation-httpx>=0.46b0   # traces OpenAI HTTP calls
temporalio[opentelemetry]>=1.7                # Temporal's contrib package
tiktoken>=0.7                                 # client-side token counting, zero API calls
```

---

## Phase 3 — OTEL Bootstrap Module

**New file: `backend/observability/otel.py`**

```python
# Initializes TracerProvider + MeterProvider + LoggerProvider
# Exports via OTLP gRPC to the OTEL Collector
# Called once at process startup (main.py AND worker.py)
def configure_otel(service_name: str) -> None: ...
```

**New file: `backend/observability/metrics.py`**

```python
# Custom RAG instruments — imported by activities
rag_retrieval_latency   = Histogram("rag.retrieval.latency_ms", ...)
rag_llm_tokens          = Counter("rag.llm.tokens_total", ...)
rag_retrieval_score     = Histogram("rag.retrieval.score_avg", ...)
rag_chunks_retrieved    = Histogram("rag.reranker.docs_out", ...)
rag_activity_retries    = Counter("rag.workflow.retries_total", ...)
doc_chunks_produced     = Histogram("doc.chunks_produced", ...)
doc_processing_latency  = Histogram("doc.processing_latency_ms", ...)
```

---

## Phase 4 — FastAPI Instrumentation (`main.py`)

```python
configure_otel("aktilot-api")
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument()
```

Gives: auto spans for every HTTP route + every DB query, propagated trace IDs.

---

## Phase 5 — Temporal Instrumentation

**`temporal/client.py`** — add `OpenTelemetryInterceptor` to client:

```python
from temporalio.contrib.opentelemetry import TracingInterceptor
client = await Client.connect(..., interceptors=[TracingInterceptor()])
```

**`temporal/worker.py`** — add interceptor to worker + call `configure_otel("aktilot-worker")`:

```python
worker = Worker(..., interceptors=[TracingInterceptor()])
```

This automatically creates **parent spans** for each workflow execution and **child spans** for every activity, all linked to the same trace that started at the FastAPI HTTP request. The full end-to-end trace becomes:

```
POST /api/chat → ChatWorkflow → extract_keywords → embed_query → search_vectors → hybrid_rank → generate_answer → persist_messages
```

---

## Phase 6 — Custom Metrics in Activities

### Naming Convention

All custom instruments follow this schema:

```
rag.<subsystem>.<metric_noun>[_<unit>]
```

| Rule | Example |
|---|---|
| Dots as namespace separators | `rag.retrieval.latency_ms` |
| Unit suffix for ambiguous metrics | `_ms`, `_tokens`, `_bytes`, `_total` |
| Lowercase snake_case throughout | `time_to_first_token_ms` |
| No verb in metric name — verb is the type | Counter = `_total`, Histogram = distribution noun |
| `_total` suffix on Counters only | `rag.llm.requests_total` |

All metrics carry the **Common Attributes** (defined in section 9) as OTel resource or span attributes. Labels listed per metric are the *additional* attributes beyond the common set.

---

### 6.1 Retrieval Metrics

Recorded across two activities: `search_vectors` (vector phase) and `hybrid_rank` (scoring phase). The split lets you isolate where latency originates.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.retrieval.latency_ms` | Histogram | `retrieval_strategy` | `search_vectors` + `hybrid_rank` combined | End-to-end retrieval P99 — first metric to check when answers are slow |
| `rag.retrieval.vector_search_latency_ms` | Histogram | `collection_name` | `search_vectors`, wrapped around `chroma_search()` | Isolates ChromaDB from BM25; rules out vector DB as latency source |
| `rag.retrieval.bm25_latency_ms` | Histogram | — | `hybrid_rank`, time around `BM25Okapi(corpus).get_scores()` only | BM25 is CPU-bound; spikes here mean large corpus or starved worker |
| `rag.retrieval.hybrid_latency_ms` | Histogram | — | `hybrid_rank`, total activity wall time | Full reranking overhead; subtract `bm25_latency_ms` to get sort/merge cost |
| `rag.retrieval.top_k_requested` | Histogram | `collection_name` | `search_vectors`, value of `k` argument | Tracks agent configuration drift; should be stable for a given agent |
| `rag.retrieval.top_k_returned` | Histogram | `collection_name` | `search_vectors`, `len(results)` after call | When `returned < requested` the collection is too sparse for that query |
| `rag.retrieval.score_avg` | Histogram | `collection_name`, `score_type` (`vector`/`bm25`/`hybrid`) | `hybrid_rank`, average of `final_score` across `ranked` | Declining trend = retrieval quality degrading; actionable before users complain |
| `rag.retrieval.score_max` | Histogram | `collection_name`, `score_type` | `hybrid_rank`, `ranked[0]['score']` | Ceiling of what the best chunk achieved; low ceiling = content gap |
| `rag.retrieval.score_min` | Histogram | `collection_name`, `score_type` | `hybrid_rank`, `ranked[-1]['score']` | Floor quality; high spread between max and min = inconsistent corpus |
| `rag.retrieval.empty_total` | Counter | `collection_name`, `reason` (`no_vectors`/`below_threshold`) | `search_vectors` when `len(results) == 0` | Spikes = document not ingested, collection deleted, or query out-of-domain |
| `rag.retrieval.keyword_hits_avg` | Histogram | — | `hybrid_rank`, `avg(c['kw_hits'] for c in ranked)` | Low keyword hits despite non-empty results = vector search working but lexical gap |

**Recording notes:**

`search_vectors` currently calls `chroma_search(project_id, query_vector, k=20)` with `k=20` hardcoded. Record `top_k_requested=20` as the argument and `top_k_returned=len(results)` from the response. For `score_type` breakdown, record three observations of `score_avg` per query — one for `vec_score`, one for `bm25_score`, one for `hybrid` — using the `score_type` label. All three values are already computed at lines 120–141 of `chat_activities.py`.

---

### 6.2 Reranker Metrics

All recorded inside `hybrid_rank`. The current reranker is BM25 + linear combination. These metrics answer "is the reranker adding value or just adding latency?"

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.reranker.latency_ms` | Histogram | `reranker_type` (`bm25_hybrid`) | `hybrid_rank` total wall time | Baseline cost of reranking; compare against retrieval benefit |
| `rag.reranker.docs_in` | Histogram | `reranker_type` | `hybrid_rank`, `len(raw_results)` before scoring | If consistently equal to `top_k_requested`, vector search is the true ceiling |
| `rag.reranker.docs_out` | Histogram | `reranker_type` | `hybrid_rank`, `len(ranked)` = `top_k` | Should always equal `config['top_k']`; deviations mean config drift |
| `rag.reranker.docs_discarded` | Histogram | `reranker_type` | `hybrid_rank`, `docs_in - docs_out` | High and rising = vector search over-fetches; low = under-fetches |
| `rag.reranker.score_avg` | Histogram | `reranker_type` | `hybrid_rank`, `mean(c['score'] for c in ranked)` | Falling average = corpus quality issue or query drift |
| `rag.reranker.score_top1` | Histogram | `reranker_type` | `hybrid_rank`, `ranked[0]['score']` | Most important retrieval quality signal; below 0.4 = poor match |

**Recording notes:**

All six values are computable from data already present at the end of `hybrid_rank`. No additional computation required — only recording calls. `docs_discarded` = `len(raw_results) - len(ranked[:top_k])`.

---

### 6.3 Prompt Metrics

Recorded inside `generate_answer`. The context string is built in-workflow (deterministic, no activity), but `generate_answer` receives `question`, `context`, and `system_prompt` as parameters, so all three components are available for token counting via `tiktoken.encoding_for_model(model)` — a local CPU operation, zero network cost.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.prompt.build_latency_ms` | Histogram | — | `generate_answer`, time to format the final messages list before API call | Captures template rendering; should be sub-millisecond; spikes indicate serialization bug |
| `rag.prompt.tokens_system` | Histogram | `model` | `generate_answer`, `tiktoken.count(system_prompt)` | System prompts are static cost per query; large ones waste tokens on every request |
| `rag.prompt.tokens_user_question` | Histogram | `model` | `generate_answer`, `tiktoken.count(question)` | Tracks whether users are sending increasingly long queries over time |
| `rag.prompt.tokens_context` | Histogram | `model` | `generate_answer`, `tiktoken.count(context)` | Largest component of input cost; rising trend = chunks too large or too many |
| `rag.prompt.tokens_total_input` | Histogram | `model` | `generate_answer`, sum of all three above | Total input budget consumed; validate against `response.usage.prompt_tokens` |
| `rag.prompt.chunks_included` | Histogram | — | `generate_answer` (add `chunks_count` parameter) | If `chunks_included < top_k`, context builder filters; if equal, top_k may be too high |
| `rag.prompt.context_chars` | Histogram | — | `generate_answer`, `len(context)` | Cheap proxy for context size without tiktoken; use for quick dashboards |

**Prompt version attribute:** Attach `rag.prompt_version` as a span attribute on the `generate_answer` span whenever a named prompt template is used. This enables filtering all metrics by prompt version during A/B tests without a separate metric.

**Recording notes:**

`generate_answer` needs one additional parameter: `chunks_count: int`. The workflow at line 150 of `chat_workflow.py` currently passes `question`, `context`, `system_prompt` — add `len(ranked)` as a fourth argument. Minimal signature change, no logic impact.

---

### 6.4 LLM Metrics

Recorded in `extract_keywords` and `generate_answer`. Each activity calls OpenAI for a different purpose — separated via the `rag.llm.purpose` attribute (`generate` vs `keyword_extract`).

**Time To First Token (TTFT)** requires switching `generate_answer` to use `stream=True`. This is an instrumentation change only — the streaming response is consumed and concatenated before returning the string. Gate it with a config flag initially.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.llm.request_latency_ms` | Histogram | `model`, `provider`, `purpose` | Both LLM activities, wall time of `chat.completions.create` | Total time blocked waiting for OpenAI; break by purpose to separate costs |
| `rag.llm.time_to_first_token_ms` | Histogram | `model`, `provider` | `generate_answer` with streaming, time to first non-empty chunk | Users perceive TTFT as "responsiveness"; required for streaming UX optimization |
| `rag.llm.streaming_duration_ms` | Histogram | `model`, `provider` | `generate_answer` streaming, time from first to last token | Completion generation speed; subtract TTFT from total latency to get this |
| `rag.llm.tokens_input` | Histogram | `model`, `provider`, `purpose` | Both activities, `response.usage.prompt_tokens` | Per-request input cost distribution; P99 shows worst-case prompt size |
| `rag.llm.tokens_output` | Histogram | `model`, `provider`, `purpose` | Both activities, `response.usage.completion_tokens` | Output tokens cost more per token; long answers = more cost and latency |
| `rag.llm.tokens_total` | Histogram | `model`, `provider`, `purpose` | Both activities, `response.usage.total_tokens` | Quick single-metric cost proxy |
| `rag.llm.tokens_per_second` | Histogram | `model`, `provider` | `generate_answer`, `output_tokens / (latency_ms / 1000.0)` | Model throughput; stable under normal conditions; drops signal API degradation |
| `rag.llm.requests_total` | Counter | `model`, `provider`, `purpose`, `finish_reason` | Both activities after completion | `finish_reason=length` = truncation (max_tokens hit); `stop` is normal |

**Recording notes:**

All three OpenAI response fields (`prompt_tokens`, `completion_tokens`, `total_tokens`) are returned by the non-streaming API in `response.usage` — zero extra cost to read them. For `tokens_per_second`, compute as `completion_tokens / (request_latency_ms / 1000.0)`. `response.choices[0].finish_reason` is already in the response object — record it as both a metric label on `requests_total` and a span attribute on every LLM activity span.

---

### 6.5 Embedding Metrics

Recorded in `embed_query` (single vector, query time) and `embed_and_index_chunks` (batch, ingestion time). The `call_site` label (`query` vs `chunk_batch`) separates the two usage patterns.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.embedding.latency_ms` | Histogram | `model`, `provider`, `call_site` | Both embedding activities, wall time of `embeddings.create` | Ingestion batch latency should scale with batch size; query latency should be flat |
| `rag.embedding.tokens_total` | Counter | `model`, `provider`, `call_site` | Both activities, `response.usage.total_tokens` | Embedding tokens accumulate during ingestion spikes; rising = large docs or frequent re-ingestion |
| `rag.embedding.requests_total` | Counter | `model`, `provider`, `call_site` | Both activities, one increment per API call | Call rate; for chunk batching, this is calls per document not per chunk |
| `rag.embedding.batch_size` | Histogram | `model`, `call_site` | `embed_and_index_chunks`, `len(chunks)` sent per API call | Suboptimal batch sizes waste per-call overhead; should approach OpenAI's max input limit |
| `rag.embedding.dimensions` | Gauge | `model` | `embed_query`, `len(response.data[0].embedding)` — set once via module-level cache | Model validation; if dimensions change, ChromaDB collection becomes incompatible |

**Recording notes:**

The OpenAI embeddings API returns `response.usage.total_tokens`. The `embed_and_index_chunks` activity currently calls `_embed(chunks)` from `services/project_chunk_service.py` — the usage object needs to be returned from that helper for recording. For `rag.embedding.dimensions`, record only when first observed or when changed — use a module-level cache to avoid recording on every call.

---

### 6.6 Vector Database Metrics

Recorded in `search_vectors` (read path) and `embed_and_index_chunks` (write path). ChromaDB's Python client is synchronous — wrap calls with `time.perf_counter()` since `asyncio` time is unreliable for sync I/O.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.vectordb.search_latency_ms` | Histogram | `collection_name`, `provider` (`chroma`) | `search_vectors`, wrap `chroma_search()` call | Isolates ChromaDB read latency from BM25; persistent spikes = index fragmentation |
| `rag.vectordb.insert_latency_ms` | Histogram | `collection_name`, `provider` | `embed_and_index_chunks`, wrap `add_chunks()` call | Slow inserts indicate ChromaDB under memory pressure or disk I/O saturation |
| `rag.vectordb.collection_size` | Gauge | `collection_name`, `provider` | `embed_and_index_chunks` after insert, query `collection.count()` | Growth rate per collection; exponential growth = runaway ingestion or duplicate uploads |
| `rag.vectordb.query_count_total` | Counter | `collection_name`, `provider` | `search_vectors`, one increment per call | Per-collection query rate; identifies hot collections that need dedicated resources |
| `rag.vectordb.insert_count_total` | Counter | `collection_name`, `provider` | `embed_and_index_chunks`, one increment per batch | Insert rate; combined with `collection_size` gives chunks-per-insert |

**Recording notes:**

`collection.count()` is a cheap metadata call in ChromaDB that does not scan embeddings. Call it once after `add_chunks()` returns — the cost is negligible relative to the insert itself. The collection name in Aktilot is the `project_id` (ChromaDB uses this as the collection name), so `collection_name = project_id`.

---

### 6.7 Workflow Metrics

Temporal's `TracingInterceptor` automatically creates spans. These custom metrics complement the traces with aggregatable time-series data in Prometheus.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.workflow.duration_ms` | Histogram | `workflow_type`, `status` (`completed`/`failed`) | Workflow completion via `ExecutionInterceptor` | End-to-end duration per workflow type; P99 ChatWorkflow tells you SLA compliance |
| `rag.workflow.activity_duration_ms` | Histogram | `activity_name`, `workflow_type` | Activity completion interceptor | Breaks down which activity dominates workflow wall time; drives optimization priority |
| `rag.workflow.queue_delay_ms` | Histogram | `activity_name` | Activity start interceptor — `info().scheduled_time` to `start_time` | High queue delay = worker overloaded; not a code bug but an infrastructure signal |
| `rag.workflow.retries_total` | Counter | `activity_name`, `error_type` | Activity on `activity.info().attempt > 1` at start | Retry hotspot map; `embed_and_index_chunks` retrying most = OpenAI instability |
| `rag.workflow.failures_total` | Counter | `workflow_type`, `error_type` | Workflow failure interceptor | Terminal failures (all retries exhausted); separate from transient retries |
| `rag.workflow.activity_failures_total` | Counter | `activity_name`, `error_type`, `non_retryable` | Activity exception interceptor | Non-retryable failures are config or auth errors requiring human action |

**Recording notes:**

Temporal's `ActivityInboundInterceptor` provides `execute_activity` hooks where you can wrap the call and observe `activity.info().attempt`, `scheduled_time`, and the exception type. This is distinct from the `TracingInterceptor` and coexists with it. `workflow_type` is available from `activity.info().workflow_type` inside activity code.

---

### 6.8 Token and Cost Metrics

Pure Counters — monotonically increasing totals that Grafana can `rate()` over time and eventually multiply by per-token pricing. No dollar conversion yet.

| Metric | Type | Additional Labels | Where | Why |
|---|---|---|---|---|
| `rag.tokens.input_total` | Counter | `model`, `provider`, `purpose` | `extract_keywords` + `generate_answer`, `response.usage.prompt_tokens` | Running total of LLM input tokens per model and purpose — the primary cost accumulator |
| `rag.tokens.output_total` | Counter | `model`, `provider`, `purpose` | Same activities, `response.usage.completion_tokens` | Output costs more per token on most models; track separately |
| `rag.tokens.embedding_total` | Counter | `model`, `provider`, `call_site` | `embed_query` + `embed_and_index_chunks`, `response.usage.total_tokens` | Embedding volume; large during ingestion spikes, flat during normal chat |
| `rag.requests.chat_total` | Counter | `model`, `provider`, `purpose`, `finish_reason` | Both LLM activities | Request count by purpose; `keyword_extract` should be 1:1 with `generate`; deviation = bug |
| `rag.requests.embedding_total` | Counter | `model`, `provider`, `call_site` | Both embedding activities | Embedding request rate; ingestion = bursty, query = steady; alerts on unexpected spikes |

**Cost dashboard bridge:** When ready to add dollar cost, multiply `rag.tokens.input_total` and `rag.tokens.output_total` by a per-model rate in Grafana using a recording rule or a `transform`. No code change required.

---

### 6.9 Common Attributes

These attributes are attached to every span and metric observation wherever applicable. Set once per activity/workflow execution, not per-metric-observation.

**Naming:** All RAG-specific attributes use the `rag.` prefix. OTel semantic conventions (`service.*`, `deployment.*`) are kept as-is for compatibility with Grafana's service discovery.

| Attribute | Source | Applies To | Notes |
|---|---|---|---|
| `service.name` | OTel resource | All | `aktilot-api` or `aktilot-worker` |
| `service.version` | OTel resource, from `settings.app_version` | All | Enables "did this break after deploy?" queries |
| `deployment.environment` | OTel resource, from `settings.environment` | All | `dev` / `staging` / `production` |
| `rag.project_id` | Activity args or `workflow.info()` | Retrieval, VectorDB, Embedding | The logical tenant; all per-project metrics filter on this |
| `rag.agent_id` | `get_agent_config` args | Chat activities | Links metrics to agent configuration (top_k, system_prompt) |
| `rag.workflow_id` | `workflow.info().workflow_id` or `activity.info().workflow_id` | All Temporal activities | Correlates metrics back to a specific Temporal trace in Tempo |
| `rag.workflow_type` | `activity.info().workflow_type` | All Temporal activities | Separates `ChatWorkflow` from `DocumentWorkflow` aggregates |
| `rag.activity_name` | `activity.info().activity_type` | All Temporal activities | Drilldown from workflow to specific step |
| `rag.collection_name` | `project_id` (ChromaDB collection name = project_id) | VectorDB, Retrieval | Matches ChromaDB collection for cross-referencing |
| `rag.model` | `settings.chat_model` | LLM activities | Enables model comparison when switching models |
| `rag.embedding_model` | `settings.embedding_model` | Embedding activities | Tracks embedding model version separately from chat model |
| `rag.provider` | Hardcoded `openai` initially | LLM + Embedding activities | Ready for multi-provider expansion |
| `rag.retrieval_strategy` | Hardcoded `hybrid` for current code | Retrieval activities | When pure-vector or pure-BM25 paths are added, this differentiates them |
| `rag.top_k_requested` | `config['top_k']` from `get_agent_config` | Retrieval, Reranker | Correlates retrieval config to quality outcomes |
| `rag.reranker_enabled` | `true` (always, current code) | Reranker | Ready for when reranker becomes optional |
| `rag.prompt_version` | Optional — set in `generate_answer` if prompt templates are versioned | Prompt, LLM | A/B test filter; set to `default` if no versioning yet |
| `rag.finish_reason` | `response.choices[0].finish_reason` | LLM activities | Surface as both a metric label and a span attribute |

**Attribute propagation pattern:** Set `rag.project_id`, `rag.workflow_id`, and `rag.agent_id` on the Temporal activity's span at the top of each activity function using `activity.info()` and the activity arguments. All metric observations made within that activity will then inherit these attributes via the active OTel context.

---

## Phase 7 — Grafana Dashboards

Six purpose-built dashboards, each answering a specific engineering question. All histograms expose Prometheus exemplars so any P99 spike can link directly to the matching Tempo trace with one click.

---

### Dashboard 1: RAG Pipeline Overview

Landing page — high-level health before drilling down.

| Panel | Metric | Visualization |
|---|---|---|
| End-to-end chat latency (P50/P95/P99) | `rag.workflow.duration_ms{workflow_type=ChatWorkflow}` | Time series with threshold lines |
| Workflow success rate | `1 - rate(rag.workflow.failures_total) / rate(rag.requests.chat_total)` | Stat panel |
| Active retry hotspots | `topk(5, rate(rag.workflow.retries_total[5m]))` | Bar chart by `activity_name` |
| Request rate by workflow type | `rate(rag.requests.chat_total[5m])` | Time series |
| Activity duration breakdown | `rag.workflow.activity_duration_ms` | Stacked bar by `activity_name` (shows which step dominates) |

---

### Dashboard 2: Retrieval Quality

Answers: "Why did retrieval quality drop?" and "Why are users retrieving too many chunks?"

| Panel | Metric | Visualization |
|---|---|---|
| Hybrid score distribution | `rag.retrieval.score_avg{score_type=hybrid}` | Histogram heatmap over time |
| Top-1 score trend | `rag.reranker.score_top1` | Time series with alert threshold at 0.4 |
| Top-K requested vs returned | `rag.retrieval.top_k_requested` vs `rag.retrieval.top_k_returned` | Dual time series |
| Empty retrieval rate | `rate(rag.retrieval.empty_total[5m])` | Stat panel with red threshold |
| Vector vs BM25 score split | `rag.retrieval.score_avg{score_type=vector}` and `{score_type=bm25}` | Two time series on same panel |
| Reranker discard ratio | `rag.reranker.docs_discarded / rag.reranker.docs_in` | Time series (expected stable ~0.7 for k=20→top_k=6) |
| Retrieval latency breakdown | `vector_search_latency_ms`, `bm25_latency_ms`, `hybrid_latency_ms` | Stacked bar |
| Keyword hits average | `rag.retrieval.keyword_hits_avg` | Time series |

---

### Dashboard 3: Prompt Intelligence

Answers: "Why are prompts getting larger?" and "Why did token usage increase?"

| Panel | Metric | Visualization |
|---|---|---|
| Prompt token composition | `tokens_system`, `tokens_user_question`, `tokens_context` | Stacked area chart over time |
| Context token trend by project | `rag.prompt.tokens_context` grouped by `rag.project_id` | Multi-line time series |
| System prompt tokens (should be flat) | `rag.prompt.tokens_system` | Stat panel — alert on any increase |
| User question length distribution | `rag.prompt.tokens_user_question` | Histogram |
| Chunks included vs top_k | `rag.prompt.chunks_included` vs `rag.retrieval.top_k_requested` | Dual stat panel or time series |
| Prompt build latency | `rag.prompt.build_latency_ms` | Histogram |
| Total input tokens by model | `rag.prompt.tokens_total_input` grouped by `rag.model` | Stacked bar — shows model migration impact |

---

### Dashboard 4: LLM Performance

Answers: "Why was this answer slow?" and "Why is one model more expensive?"

| Panel | Metric | Visualization |
|---|---|---|
| Time to first token (P50/P95/P99) | `rag.llm.time_to_first_token_ms` | Time series |
| Total response latency | `rag.llm.request_latency_ms{purpose=generate}` | Time series with percentile bands |
| Tokens per second | `rag.llm.tokens_per_second` | Time series (stable = healthy) |
| Input vs output token ratio | `rag.llm.tokens_input / rag.llm.tokens_output` | Time series — rising ratio = long answers |
| Finish reason distribution | `rag.llm.requests_total` by `finish_reason` | Pie chart — `length` slices = truncation |
| Keyword extraction latency | `rag.llm.request_latency_ms{purpose=keyword_extract}` | Histogram |
| LLM latency by model | `rag.llm.request_latency_ms` grouped by `rag.model` | Multi-line time series for model comparison |
| Request volume by purpose | `rate(rag.requests.chat_total[5m])` by `purpose` | Bar chart |

---

### Dashboard 5: Vector Database Health

Answers: "Which collections are growing rapidly?" and "Is ChromaDB under pressure?"

| Panel | Metric | Visualization |
|---|---|---|
| Collection size over time | `rag.vectordb.collection_size` by `collection_name` | Multi-line time series (growth curves) |
| Search latency (P50/P95/P99) | `rag.vectordb.search_latency_ms` | Time series |
| Insert latency | `rag.vectordb.insert_latency_ms` | Time series |
| Query rate by collection | `rate(rag.vectordb.query_count_total[5m])` by `collection_name` | Bar chart — hot collection identification |
| Insert rate | `rate(rag.vectordb.insert_count_total[5m])` | Time series — ingestion spike detection |
| Embedding batch size distribution | `rag.embedding.batch_size` | Histogram |

---

### Dashboard 6: Token and Cost Intelligence

Answers: "Why did token usage increase?" and "Why is reranking not helping?"

| Panel | Metric | Visualization |
|---|---|---|
| Hourly input token rate by model | `rate(rag.tokens.input_total[1h])` by `rag.model` | Stacked area |
| Hourly output token rate | `rate(rag.tokens.output_total[1h])` by `purpose` | Time series |
| Embedding token rate (ingestion vs query) | `rate(rag.tokens.embedding_total[1h])` by `call_site` | Two-line chart |
| Token efficiency ratio | `tokens_output / tokens_input` per query | Time series — rising = increasingly verbose answers |
| Chat vs embedding request ratio | `rate(rag.requests.chat_total) / rate(rag.requests.embedding_total)` | Stat panel |
| LLM requests by finish reason | `rag.requests.chat_total` by `finish_reason` | Bar chart over time |
| Embedding requests by site | `rate(rag.requests.embedding_total[5m])` by `call_site` | Time series |

---

## Phase 8 — Trace Correlation

Because Temporal's `TracingInterceptor` propagates trace context through workflow history, and FastAPI injects the trace ID into HTTP response headers, every metric panel in all six dashboards can link to a Tempo trace via exemplars.

The full trace structure for a chat request:

```
POST /api/chat  [FastAPI span]
  └── ChatWorkflow  [Temporal workflow span]
        ├── get_agent_config      [activity span + DB query span]
        ├── extract_keywords      [activity span + LLM latency, token counts as span events]
        ├── embed_query           [activity span + embedding latency, dimensions]
        ├── search_vectors        [activity span + ChromaDB span, top_k_returned]
        ├── hybrid_rank           [activity span + BM25 timing, score_top1, docs_discarded]
        ├── generate_answer       [activity span + prompt token breakdown, TTFT, finish_reason]
        └── persist_messages      [activity span + DB write span]
```

The trace carries `rag.project_id`, `rag.agent_id`, and `rag.workflow_id` as attributes on every span, so any Grafana panel filtered by project can jump to the matching trace without manual correlation.

---

## File Change Summary

| File | Change |
|---|---|
| `docker-compose.yml` | Add otel-collector, prometheus, tempo, grafana services |
| `otel-collector-config.yaml` | New — OTLP receiver, Prometheus + Tempo exporters |
| `prometheus.yml` | New — scrape config |
| `grafana/provisioning/` | New — datasources + dashboard provisioning |
| `backend/requirements.txt` | Add 5 OTel packages + `tiktoken` |
| `backend/observability/otel.py` | New — provider bootstrap |
| `backend/observability/metrics.py` | New — all custom instruments (histograms, counters, gauges) |
| `backend/main.py` | Add FastAPI + SQLAlchemy instrumentation |
| `backend/temporal/client.py` | Add `TracingInterceptor` |
| `backend/temporal/worker.py` | Add `TracingInterceptor` + `configure_otel("aktilot-worker")` |
| `backend/temporal/activities/chat_activities.py` | Add metric recording across all 7 activities |
| `backend/temporal/activities/document_activities.py` | Add metric recording in `embed_and_index_chunks` |

---

## Key Design Decisions

1. **OTEL Collector as the single egress point** — services only speak OTLP; the collector fans out to Prometheus, Tempo, and optionally Loki. Swapping backends later requires only collector config changes, not code changes.

2. **Temporal's built-in interceptor** — avoids manual span creation in workflow code. Temporal's deterministic replay constraint means you cannot call OTel APIs directly inside `@workflow.defn` — the interceptor handles this correctly.

3. **Metrics + Traces linked by `trace_id`** — Grafana's exemplar support on Prometheus histograms lets you jump from a slow P99 bar directly to the Tempo trace, without manual correlation.

4. **`tiktoken` for client-side token counting** — counts prompt tokens before each LLM call using the same BPE encoding as OpenAI, with zero API overhead. Validates against `response.usage.prompt_tokens` after the call.

5. **No evaluation frameworks in Phase 1** — all metrics are collected as a side effect of normal request processing. Ragas, DeepEval, or LLM-as-a-Judge can be layered on later without touching the observability infrastructure.

6. **No Loki required initially** — structured JSON logging to stdout + the OTel log bridge is sufficient. Loki can be added later with a single collector pipeline addition.

7. **No dollar cost in Phase 1** — raw token counters (`rag.tokens.input_total`, `rag.tokens.output_total`) are exposed. Cost dashboards are built in Grafana by multiplying these counters by a per-model rate via a recording rule or transform. No code change required when pricing updates.
