"""
All custom OpenTelemetry instruments for the Aktilot RAG platform.

Import the instruments you need from this module inside activity functions —
they are lazily resolved against the global MeterProvider so there is no
import-order dependency on configure_otel().

Instrument categories (matching the plan sections):
  6.1  Retrieval metrics
  6.2  Reranker metrics
  6.3  Prompt metrics
  6.4  LLM metrics
  6.5  Embedding metrics
  6.6  Vector database metrics
  6.7  Workflow metrics
  6.8  Token and cost metrics (raw counters, no $ conversion)
"""

from opentelemetry import metrics
from opentelemetry.metrics import Observation

_meter = metrics.get_meter("aktilot.rag", version="0.1.0")

# ── Persistent gauge caches ───────────────────────────────────────────────────
# ObservableGauge callbacks read from these dicts so values survive across
# export cycles (unlike synchronous Gauge which only emits when set() is called
# within the active collection window).
_vectordb_size_cache: dict[tuple[str, str], int] = {}
_embedding_dim_cache: dict[str, int] = {}


def update_vectordb_size(project_id: str, collection_name: str, size: int) -> None:
    _vectordb_size_cache[(project_id, collection_name)] = size


def update_embedding_dims(model: str, dims: int) -> None:
    _embedding_dim_cache[model] = dims


def _observe_vectordb_sizes(options):
    for (project_id, coll_name), size in list(_vectordb_size_cache.items()):
        yield Observation(
            size, {"rag.project_id": project_id, "rag.collection_name": coll_name}
        )


def _observe_embedding_dims(options):
    for model, dims in list(_embedding_dim_cache.items()):
        yield Observation(dims, {"rag.model": model})


# ── 6.1  Retrieval ────────────────────────────────────────────────────────────

retrieval_latency = _meter.create_histogram(
    "rag.retrieval.latency_ms",
    unit="ms",
    description="End-to-end retrieval latency (vector search + reranking combined)",
)

retrieval_vector_search_latency = _meter.create_histogram(
    "rag.retrieval.vector_search_latency_ms",
    unit="ms",
    description="ChromaDB vector search wall time, isolated from BM25",
)

retrieval_bm25_latency = _meter.create_histogram(
    "rag.retrieval.bm25_latency_ms",
    unit="ms",
    description="BM25 scoring wall time inside hybrid_rank (CPU-bound)",
)

retrieval_hybrid_latency = _meter.create_histogram(
    "rag.retrieval.hybrid_latency_ms",
    unit="ms",
    description="Total hybrid_rank activity wall time (BM25 + sort + merge)",
)

retrieval_top_k_requested = _meter.create_histogram(
    "rag.retrieval.top_k_requested",
    description="Number of results requested from the vector store per query",
)

retrieval_top_k_returned = _meter.create_histogram(
    "rag.retrieval.top_k_returned",
    description="Number of results actually returned by the vector store per query",
)

retrieval_score_avg = _meter.create_histogram(
    "rag.retrieval.score_avg",
    description=(
        "Average retrieval score per query. Record three observations per query: "
        "score_type=vector, score_type=bm25, score_type=hybrid"
    ),
)

retrieval_score_max = _meter.create_histogram(
    "rag.retrieval.score_max",
    description="Score of the top-ranked chunk per query (ceiling quality signal)",
)

retrieval_score_min = _meter.create_histogram(
    "rag.retrieval.score_min",
    description="Score of the lowest-ranked returned chunk per query (floor quality signal)",
)

retrieval_empty_total = _meter.create_counter(
    "rag.retrieval.empty_total",
    description="Number of queries that returned zero results from the vector store",
)

retrieval_keyword_hits_avg = _meter.create_histogram(
    "rag.retrieval.keyword_hits_avg",
    description="Average number of keyword matches per returned chunk",
)

# ── 6.2  Reranker ─────────────────────────────────────────────────────────────

reranker_latency = _meter.create_histogram(
    "rag.reranker.latency_ms",
    unit="ms",
    description="Total hybrid_rank activity wall time (same gate as hybrid_latency, different label set)",
)

reranker_docs_in = _meter.create_histogram(
    "rag.reranker.docs_in",
    description="Number of candidate chunks fed into the reranker",
)

reranker_docs_out = _meter.create_histogram(
    "rag.reranker.docs_out",
    description="Number of chunks returned after reranking (= top_k)",
)

reranker_docs_discarded = _meter.create_histogram(
    "rag.reranker.docs_discarded",
    description="Number of chunks filtered out by the reranker (docs_in - docs_out)",
)

reranker_score_avg = _meter.create_histogram(
    "rag.reranker.score_avg",
    description="Mean final hybrid score across the top-k chunks returned",
)

reranker_score_top1 = _meter.create_histogram(
    "rag.reranker.score_top1",
    description="Hybrid score of the best-ranked chunk — primary retrieval quality signal",
)

# ── 6.3  Prompt ───────────────────────────────────────────────────────────────

prompt_build_latency = _meter.create_histogram(
    "rag.prompt.build_latency_ms",
    unit="ms",
    description="Time to format the final messages list before the LLM API call",
)

prompt_tokens_system = _meter.create_histogram(
    "rag.prompt.tokens_system",
    unit="tokens",
    description="tiktoken count of the system prompt per generate_answer call",
)

prompt_tokens_user_question = _meter.create_histogram(
    "rag.prompt.tokens_user_question",
    unit="tokens",
    description="tiktoken count of the user question per generate_answer call",
)

prompt_tokens_context = _meter.create_histogram(
    "rag.prompt.tokens_context",
    unit="tokens",
    description="tiktoken count of the retrieved context string per generate_answer call",
)

prompt_tokens_total_input = _meter.create_histogram(
    "rag.prompt.tokens_total_input",
    unit="tokens",
    description="Sum of system + user + context tokens (pre-call estimate via tiktoken)",
)

prompt_chunks_included = _meter.create_histogram(
    "rag.prompt.chunks_included",
    description="Number of retrieved chunks actually included in the context string",
)

prompt_context_chars = _meter.create_histogram(
    "rag.prompt.context_chars",
    unit="chars",
    description="Character length of the assembled context string (cheap proxy for token size)",
)

# ── 6.4  LLM ──────────────────────────────────────────────────────────────────

llm_request_latency = _meter.create_histogram(
    "rag.llm.request_latency_ms",
    unit="ms",
    description="Wall time of a chat.completions.create call",
)

llm_time_to_first_token = _meter.create_histogram(
    "rag.llm.time_to_first_token_ms",
    unit="ms",
    description="Time from sending the request to receiving the first streaming token",
)

llm_streaming_duration = _meter.create_histogram(
    "rag.llm.streaming_duration_ms",
    unit="ms",
    description="Time from first token to last token during streaming generation",
)

llm_tokens_input = _meter.create_histogram(
    "rag.llm.tokens_input",
    unit="tokens",
    description="Input (prompt) tokens from response.usage.prompt_tokens per LLM call",
)

llm_tokens_output = _meter.create_histogram(
    "rag.llm.tokens_output",
    unit="tokens",
    description="Output (completion) tokens from response.usage.completion_tokens per LLM call",
)

llm_tokens_total = _meter.create_histogram(
    "rag.llm.tokens_total",
    unit="tokens",
    description="Total tokens from response.usage.total_tokens per LLM call",
)

llm_tokens_per_second = _meter.create_histogram(
    "rag.llm.tokens_per_second",
    unit="tokens/s",
    description="Output tokens divided by request latency — model throughput signal",
)

llm_requests_total = _meter.create_counter(
    "rag.llm.requests_total",
    description="Number of LLM API calls. finish_reason label distinguishes stop vs length (truncation)",
)

# ── 6.5  Embedding ────────────────────────────────────────────────────────────

embedding_latency = _meter.create_histogram(
    "rag.embedding.latency_ms",
    unit="ms",
    description="Wall time of an embeddings.create call",
)

embedding_tokens_total = _meter.create_counter(
    "rag.embedding.tokens_total",
    unit="tokens",
    description="Cumulative tokens consumed by embedding API calls",
)

embedding_requests_total = _meter.create_counter(
    "rag.embedding.requests_total",
    description="Number of embedding API calls",
)

embedding_batch_size = _meter.create_histogram(
    "rag.embedding.batch_size",
    description="Number of text chunks sent per embedding API call",
)

embedding_dimensions = _meter.create_observable_gauge(
    "rag.embedding.dimensions",
    callbacks=[_observe_embedding_dims],
    description="Dimension count of embedding vectors (model validation; should be stable)",
)

# ── 6.6  Vector Database ──────────────────────────────────────────────────────

vectordb_search_latency = _meter.create_histogram(
    "rag.vectordb.search_latency_ms",
    unit="ms",
    description="ChromaDB collection.query() wall time",
)

vectordb_insert_latency = _meter.create_histogram(
    "rag.vectordb.insert_latency_ms",
    unit="ms",
    description="ChromaDB add_chunks() wall time",
)

vectordb_collection_size = _meter.create_observable_gauge(
    "rag.vectordb.collection_size",
    callbacks=[_observe_vectordb_sizes],
    description="Total number of vectors in a ChromaDB collection after each insert",
)

vectordb_query_count_total = _meter.create_counter(
    "rag.vectordb.query_count_total",
    description="Cumulative number of vector search queries per collection",
)

vectordb_insert_count_total = _meter.create_counter(
    "rag.vectordb.insert_count_total",
    description="Cumulative number of vector insert batches per collection",
)

# ── 6.7  Workflow ─────────────────────────────────────────────────────────────

workflow_duration = _meter.create_histogram(
    "rag.workflow.duration_ms",
    unit="ms",
    description="End-to-end workflow execution time from start to completion or failure",
)

workflow_activity_duration = _meter.create_histogram(
    "rag.workflow.activity_duration_ms",
    unit="ms",
    description="Individual activity execution time — use to find which step dominates",
)

workflow_queue_delay = _meter.create_histogram(
    "rag.workflow.queue_delay_ms",
    unit="ms",
    description="Time between activity scheduled and activity started (worker queue depth signal)",
)

workflow_retries_total = _meter.create_counter(
    "rag.workflow.retries_total",
    description="Number of activity retry attempts (attempt > 1). High count = dependency instability",
)

workflow_failures_total = _meter.create_counter(
    "rag.workflow.failures_total",
    description="Terminal workflow failures after all retries exhausted",
)

workflow_activity_failures_total = _meter.create_counter(
    "rag.workflow.activity_failures_total",
    description="Activity-level failures. non_retryable=true means auth/config error requiring human action",
)

# ── 6.8  Token & Cost (raw counters, no $ conversion) ────────────────────────

tokens_input_total = _meter.create_counter(
    "rag.tokens.input_total",
    unit="tokens",
    description="Cumulative LLM input (prompt) tokens — primary cost accumulator",
)

tokens_output_total = _meter.create_counter(
    "rag.tokens.output_total",
    unit="tokens",
    description="Cumulative LLM output (completion) tokens",
)

tokens_embedding_total = _meter.create_counter(
    "rag.tokens.embedding_total",
    unit="tokens",
    description="Cumulative tokens consumed by the embedding API",
)

requests_chat_total = _meter.create_counter(
    "rag.requests.chat_total",
    description="Cumulative LLM chat completion API calls",
)

requests_embedding_total = _meter.create_counter(
    "rag.requests.embedding_total",
    description="Cumulative embedding API calls",
)
