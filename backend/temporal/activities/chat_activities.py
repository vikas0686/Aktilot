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
import uuid

from openai import AsyncOpenAI, AuthenticationError, RateLimitError
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

import db.models  # noqa: F401 — side-effect import: registers all SQLAlchemy mappers
from config import settings
from db.models.agent import Agent
from db.session import AsyncSessionFactory
from services.message_service import create as create_message
from vectorstore.chroma_store import search as chroma_search

_openai = AsyncOpenAI(api_key=settings.openai_api_key)

_FALLBACK_SYSTEM_PROMPT = (
    "You are a document assistant. Use only the supplied context to answer. "
    "If the answer is not in the context say: "
    "'I could not find that information in the uploaded documents.'"
)


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
        raw = resp.choices[0].message.content or "[]"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return question.lower().split()
    except AuthenticationError as exc:
        raise ApplicationError(str(exc), type="AUTH_ERROR", non_retryable=True) from exc
    except RateLimitError as exc:
        raise ApplicationError(str(exc), type="RATE_LIMIT") from exc


@activity.defn
async def embed_query(question: str) -> list[float]:
    try:
        resp = await _openai.embeddings.create(
            model=settings.embedding_model, input=question
        )
        return resp.data[0].embedding
    except AuthenticationError as exc:
        raise ApplicationError(str(exc), type="AUTH_ERROR", non_retryable=True) from exc
    except RateLimitError as exc:
        raise ApplicationError(str(exc), type="RATE_LIMIT") from exc


@activity.defn
async def search_vectors(
    project_id: str, query_vector: list[float], keywords: list[str]
) -> list[dict]:
    # keywords arg reserved for future keyword-boosted search
    return chroma_search(project_id, query_vector, k=20)


@activity.defn
async def hybrid_rank(
    raw_results: list[dict], keywords: list[str], top_k: int
) -> list[dict]:
    if not raw_results:
        return []

    corpus = [r["content"].lower().split() for r in raw_results]
    query_tokens = " ".join(keywords).lower().split() or ["_"]
    bm25 = BM25Okapi(corpus)
    bm25_raw = bm25.get_scores(query_tokens)
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
    return [chunk for chunk, _ in scored[:top_k]]


@activity.defn
async def generate_answer(question: str, context: str, system_prompt: str) -> str:
    try:
        resp = await _openai.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
                },
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except AuthenticationError as exc:
        raise ApplicationError(str(exc), type="AUTH_ERROR", non_retryable=True) from exc
    except RateLimitError as exc:
        raise ApplicationError(str(exc), type="RATE_LIMIT") from exc


@activity.defn
async def persist_messages(agent_id: str, question: str, answer: str) -> None:
    async with AsyncSessionFactory() as db:
        await create_message(db, uuid.UUID(agent_id), "user", question)
        await create_message(db, uuid.UUID(agent_id), "assistant", answer)
