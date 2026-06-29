"""
Activities for ChatWorkflow — each step in the RAG pipeline is independently retryable.

If extract_keywords succeeds and embed_query fails, only embed_query retries.
The keyword result is already checkpointed in Temporal history — not re-run.

Error types encoded in ApplicationError.type so the route can map to HTTP status codes:
  AUTH_ERROR  → 401
  RATE_LIMIT  → 429 (retried first; 429 raised only if all retries exhausted)
  NOT_FOUND   → 404
"""

import json
import time
import uuid

import tiktoken
from openai import AsyncOpenAI, AuthenticationError, RateLimitError
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

import db.models  # noqa: F401 — side-effect import: registers all SQLAlchemy mappers
from config import settings
from db.models.agent import Agent
from db.session import AsyncSessionFactory
from observability import metrics as m
from services.message_service import create as create_message
from vectorstore.chroma_store import search as chroma_search

_openai = AsyncOpenAI(api_key=settings.openai_api_key)

_FALLBACK_SYSTEM_PROMPT = (
    "You are a document assistant. Use only the supplied context to answer. "
    "If the answer is not in the context say: "
    "'I could not find that information in the uploaded documents.'"
)

# Module-level tiktoken encoder cache — resolved lazily to avoid import-time side effects
_tiktoken_encoders: dict[str, tiktoken.Encoding] = {}


def _get_encoder(model: str) -> tiktoken.Encoding:
    if model not in _tiktoken_encoders:
        try:
            _tiktoken_encoders[model] = tiktoken.encoding_for_model(model)
        except KeyError:
            _tiktoken_encoders[model] = tiktoken.get_encoding("cl100k_base")
    return _tiktoken_encoders[model]


def _count_tokens(text: str, model: str) -> int:
    return len(_get_encoder(model).encode(text))


def _common_attrs(activity_name: str) -> dict:
    """Return common OTel attributes from the current activity context."""
    info = activity.info()
    return {
        "rag.activity_name": activity_name,
        "rag.workflow_id": info.workflow_id,
        "rag.workflow_type": info.workflow_type,
        "rag.model": settings.chat_model,
        "rag.provider": "openai",
    }


@activity.defn
async def get_agent_config(agent_id: str) -> dict:
    async with AsyncSessionFactory() as db:
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise ApplicationError(
                f"Agent {agent_id} not found",
                type="NOT_FOUND",
                non_retryable=True,
            )
        return {
            "project_id": str(agent.project_id),
            "system_prompt": agent.system_prompt.strip() or _FALLBACK_SYSTEM_PROMPT,
            "top_k": agent.top_k,
        }


@activity.defn
async def extract_keywords(question: str) -> list[str]:
    attrs = _common_attrs("extract_keywords")
    attrs["rag.llm.purpose"] = "keyword_extract"

    t0 = time.perf_counter()
    try:
        resp = await _openai.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract search keywords from this user query. "
                        "Return a JSON array of strings only, no explanation.\n"
                        f"Query: {question}"
                    ),
                }
            ],
            temperature=0,
        )
    except AuthenticationError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "AUTH_ERROR", "non_retryable": "true"}
        )
        raise ApplicationError(str(exc), type="AUTH_ERROR", non_retryable=True) from exc
    except RateLimitError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "RATE_LIMIT", "non_retryable": "false"}
        )
        raise ApplicationError(str(exc), type="RATE_LIMIT") from exc

    latency_ms = (time.perf_counter() - t0) * 1000
    usage = resp.usage
    finish_reason = resp.choices[0].finish_reason or "unknown"

    # LLM metrics
    m.llm_request_latency.record(latency_ms, {**attrs, "finish_reason": finish_reason})
    m.llm_tokens_input.record(usage.prompt_tokens, attrs)
    m.llm_tokens_output.record(usage.completion_tokens, attrs)
    m.llm_tokens_total.record(usage.total_tokens, attrs)
    if latency_ms > 0:
        m.llm_tokens_per_second.record(
            usage.completion_tokens / (latency_ms / 1000), attrs
        )
    m.llm_requests_total.add(1, {**attrs, "finish_reason": finish_reason})

    # Token cost counters
    m.tokens_input_total.add(usage.prompt_tokens, attrs)
    m.tokens_output_total.add(usage.completion_tokens, attrs)
    m.requests_chat_total.add(1, {**attrs, "finish_reason": finish_reason})

    # Retry signal
    if activity.info().attempt > 1:
        m.workflow_retries_total.add(
            1, {**attrs, "error_type": "RATE_LIMIT"}
        )

    raw = resp.choices[0].message.content or "[]"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return question.lower().split()


@activity.defn
async def embed_query(question: str) -> list[float]:
    attrs = {
        "rag.activity_name": "embed_query",
        "rag.model": settings.embedding_model,
        "rag.embedding_model": settings.embedding_model,
        "rag.provider": "openai",
        "rag.call_site": "query",
    }
    info = activity.info()
    attrs["rag.workflow_id"] = info.workflow_id
    attrs["rag.workflow_type"] = info.workflow_type

    t0 = time.perf_counter()
    try:
        resp = await _openai.embeddings.create(
            model=settings.embedding_model, input=question
        )
    except AuthenticationError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "AUTH_ERROR", "non_retryable": "true"}
        )
        raise ApplicationError(str(exc), type="AUTH_ERROR", non_retryable=True) from exc
    except RateLimitError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "RATE_LIMIT", "non_retryable": "false"}
        )
        raise ApplicationError(str(exc), type="RATE_LIMIT") from exc

    latency_ms = (time.perf_counter() - t0) * 1000
    vector = resp.data[0].embedding

    m.embedding_latency.record(latency_ms, attrs)
    m.embedding_requests_total.add(1, attrs)
    if resp.usage:
        m.embedding_tokens_total.add(resp.usage.total_tokens, attrs)
        m.tokens_embedding_total.add(resp.usage.total_tokens, attrs)
    m.requests_embedding_total.add(1, attrs)

    m.update_embedding_dims(settings.embedding_model, len(vector))

    if activity.info().attempt > 1:
        m.workflow_retries_total.add(1, {**attrs, "error_type": "RATE_LIMIT"})

    return vector


@activity.defn
async def search_vectors(
    project_id: str, query_vector: list[float], keywords: list[str]
) -> list[dict]:
    attrs = {
        "rag.activity_name": "search_vectors",
        "rag.collection_name": project_id,
        "rag.project_id": project_id,
        "rag.provider": "chroma",
        "rag.retrieval_strategy": "hybrid",
    }
    info = activity.info()
    attrs["rag.workflow_id"] = info.workflow_id
    attrs["rag.workflow_type"] = info.workflow_type

    top_k_requested = 20
    m.retrieval_top_k_requested.record(top_k_requested, attrs)

    t0 = time.perf_counter()
    results = chroma_search(project_id, query_vector, k=top_k_requested)
    vec_latency_ms = (time.perf_counter() - t0) * 1000

    top_k_returned = len(results)

    m.retrieval_vector_search_latency.record(vec_latency_ms, attrs)
    m.retrieval_top_k_returned.record(top_k_returned, attrs)
    m.vectordb_search_latency.record(vec_latency_ms, attrs)
    m.vectordb_query_count_total.add(1, attrs)

    if top_k_returned == 0:
        m.retrieval_empty_total.add(1, {**attrs, "reason": "no_vectors"})

    return results


@activity.defn
async def hybrid_rank(
    raw_results: list[dict], keywords: list[str], top_k: int
) -> list[dict]:
    attrs = {
        "rag.activity_name": "hybrid_rank",
        "rag.reranker_type": "bm25_hybrid",
        "rag.reranker_enabled": "true",
    }
    info = activity.info()
    attrs["rag.workflow_id"] = info.workflow_id
    attrs["rag.workflow_type"] = info.workflow_type

    if not raw_results:
        m.reranker_docs_in.record(0, attrs)
        m.reranker_docs_out.record(0, attrs)
        m.reranker_docs_discarded.record(0, attrs)
        return []

    docs_in = len(raw_results)
    t0 = time.perf_counter()

    # ── BM25 scoring ──────────────────────────────────────────────────────────
    t_bm25 = time.perf_counter()
    corpus = [r["content"].lower().split() for r in raw_results]
    query_tokens = " ".join(keywords).lower().split() or ["_"]
    bm25 = BM25Okapi(corpus)
    bm25_raw = bm25.get_scores(query_tokens)
    bm25_latency_ms = (time.perf_counter() - t_bm25) * 1000
    m.retrieval_bm25_latency.record(bm25_latency_ms, attrs)

    bm25_max = float(max(bm25_raw)) if float(max(bm25_raw)) > 0 else 1.0
    bm25_norm = [float(s) / bm25_max for s in bm25_raw]

    scored = []
    for i, r in enumerate(raw_results):
        vec_score = round(max(0.0, 1.0 - r["distance"]), 4)
        bm25_score = round(bm25_norm[i], 4)
        final_score = round(0.5 * vec_score + 0.5 * bm25_score, 4)
        content_lower = r["content"].lower()
        matched_kws = [kw for kw in keywords if kw.lower() in content_lower]
        scored.append(
            (
                {
                    "chunk_id": r["id"],
                    "filename": r["metadata"]["filename"],
                    "chunk_index": r["metadata"]["chunk_index"],
                    "content": r["content"],
                    "score": final_score,
                    "vec_score": vec_score,
                    "bm25_score": bm25_score,
                    "kw_hits": len(matched_kws),
                    "keywords_matched": matched_kws,
                },
                final_score,
            )
        )

    scored.sort(key=lambda x: x[1], reverse=True)
    ranked = [chunk for chunk, _ in scored[:top_k]]

    hybrid_latency_ms = (time.perf_counter() - t0) * 1000
    docs_out = len(ranked)

    # ── Reranker metrics ──────────────────────────────────────────────────────
    m.reranker_latency.record(hybrid_latency_ms, attrs)
    m.reranker_docs_in.record(docs_in, attrs)
    m.reranker_docs_out.record(docs_out, attrs)
    m.reranker_docs_discarded.record(docs_in - docs_out, attrs)

    if ranked:
        avg_score = sum(c["score"] for c in ranked) / len(ranked)
        m.reranker_score_avg.record(avg_score, attrs)
        m.reranker_score_top1.record(ranked[0]["score"], attrs)

    # ── Retrieval quality metrics (score breakdown by type) ───────────────────
    retrieval_attrs = {**attrs, "rag.activity_name": "hybrid_rank"}
    if ranked:
        avg_vec = sum(c["vec_score"] for c in ranked) / len(ranked)
        avg_bm25 = sum(c["bm25_score"] for c in ranked) / len(ranked)
        avg_hybrid = sum(c["score"] for c in ranked) / len(ranked)

        for score_val, score_type in [
            (avg_vec, "vector"),
            (avg_bm25, "bm25"),
            (avg_hybrid, "hybrid"),
        ]:
            m.retrieval_score_avg.record(
                score_val, {**retrieval_attrs, "score_type": score_type}
            )

        m.retrieval_score_max.record(
            ranked[0]["score"], {**retrieval_attrs, "score_type": "hybrid"}
        )
        m.retrieval_score_min.record(
            ranked[-1]["score"], {**retrieval_attrs, "score_type": "hybrid"}
        )

        avg_kw_hits = sum(c["kw_hits"] for c in ranked) / len(ranked)
        m.retrieval_keyword_hits_avg.record(avg_kw_hits, attrs)

    m.retrieval_hybrid_latency.record(hybrid_latency_ms, attrs)

    return ranked


@activity.defn
async def generate_answer(
    question: str, context: str, system_prompt: str, chunks_count: int = 0
) -> str:
    attrs = _common_attrs("generate_answer")
    attrs["rag.llm.purpose"] = "generate"

    # ── Prompt token counting (tiktoken, zero API cost) ───────────────────────
    t_prompt = time.perf_counter()
    model = settings.chat_model
    tokens_system = _count_tokens(system_prompt, model)
    tokens_question = _count_tokens(question, model)
    tokens_context = _count_tokens(context, model)
    tokens_total_input = tokens_system + tokens_question + tokens_context
    prompt_build_ms = (time.perf_counter() - t_prompt) * 1000

    prompt_attrs = {**attrs, "rag.model": model}
    m.prompt_build_latency.record(prompt_build_ms, prompt_attrs)
    m.prompt_tokens_system.record(tokens_system, prompt_attrs)
    m.prompt_tokens_user_question.record(tokens_question, prompt_attrs)
    m.prompt_tokens_context.record(tokens_context, prompt_attrs)
    m.prompt_tokens_total_input.record(tokens_total_input, prompt_attrs)
    m.prompt_context_chars.record(len(context), prompt_attrs)
    if chunks_count:
        m.prompt_chunks_included.record(chunks_count, prompt_attrs)

    # ── LLM call ──────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        resp = await _openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
                },
            ],
            temperature=0.2,
        )
    except AuthenticationError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "AUTH_ERROR", "non_retryable": "true"}
        )
        raise ApplicationError(str(exc), type="AUTH_ERROR", non_retryable=True) from exc
    except RateLimitError as exc:
        m.workflow_activity_failures_total.add(
            1, {**attrs, "error_type": "RATE_LIMIT", "non_retryable": "false"}
        )
        raise ApplicationError(str(exc), type="RATE_LIMIT") from exc

    latency_ms = (time.perf_counter() - t0) * 1000
    usage = resp.usage
    finish_reason = resp.choices[0].finish_reason or "unknown"
    answer = resp.choices[0].message.content or ""

    # ── LLM metrics ───────────────────────────────────────────────────────────
    llm_attrs = {**attrs, "finish_reason": finish_reason}
    m.llm_request_latency.record(latency_ms, llm_attrs)
    m.llm_tokens_input.record(usage.prompt_tokens, llm_attrs)
    m.llm_tokens_output.record(usage.completion_tokens, llm_attrs)
    m.llm_tokens_total.record(usage.total_tokens, llm_attrs)
    if latency_ms > 0 and usage.completion_tokens:
        m.llm_tokens_per_second.record(
            usage.completion_tokens / (latency_ms / 1000), attrs
        )
    m.llm_requests_total.add(1, llm_attrs)

    # ── Token cost counters ───────────────────────────────────────────────────
    m.tokens_input_total.add(usage.prompt_tokens, attrs)
    m.tokens_output_total.add(usage.completion_tokens, attrs)
    m.requests_chat_total.add(1, llm_attrs)

    if activity.info().attempt > 1:
        m.workflow_retries_total.add(1, {**attrs, "error_type": "RATE_LIMIT"})

    return answer


@activity.defn
async def persist_messages(agent_id: str, question: str, answer: str) -> None:
    async with AsyncSessionFactory() as db:
        await create_message(db, uuid.UUID(agent_id), "user", question)
        await create_message(db, uuid.UUID(agent_id), "assistant", answer)
