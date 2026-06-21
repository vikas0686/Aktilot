import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from openai import AsyncOpenAI, AuthenticationError, RateLimitError
from rank_bm25 import BM25Okapi
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.schemas import ChatResponse, RetrievedChunk, ToolStep
from services.agent_service import get as get_agent
from services.message_service import create as create_message
from vectorstore.chroma_store import search as chroma_search

client = AsyncOpenAI(api_key=settings.openai_api_key)

_FALLBACK_SYSTEM_PROMPT = (
    "You are a document assistant. Use only the supplied context to answer. "
    "If the answer is not in the context say: "
    "'I could not find that information in the uploaded documents.'"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _step(name: str, start: datetime, inp: str, out: str) -> ToolStep:
    end = datetime.now(timezone.utc)
    return ToolStep(
        name=name,
        start_time=start,
        end_time=end,
        duration_ms=(end - start).total_seconds() * 1000,
        input_summary=inp,
        output_summary=out,
    )


async def chat(db: AsyncSession, agent_id: uuid.UUID, question: str) -> ChatResponse:
    agent = await get_agent(db, agent_id)
    project_id = str(agent.project_id)
    system_prompt = agent.system_prompt.strip() or _FALLBACK_SYSTEM_PROMPT

    steps: list[ToolStep] = []

    try:
        # Step 1: Extract search keywords from the question
        t = _now()
        kw_resp = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{
                "role": "user",
                "content": (
                    "Extract search keywords from this user query. "
                    "Return a JSON array of strings only, no explanation.\n"
                    f"Query: {question}"
                ),
            }],
            temperature=0,
        )
        raw = kw_resp.choices[0].message.content or "[]"
        try:
            keywords: list[str] = json.loads(raw)
        except Exception:
            keywords = question.lower().split()
        steps.append(_step("Extract Keywords", t, question, f"Keywords: {keywords}"))

        # Step 2: Embed question and search project's ChromaDB collection
        t = _now()
        embed_resp = await client.embeddings.create(
            model=settings.embedding_model, input=question
        )
        query_vec = embed_resp.data[0].embedding
        raw_results = chroma_search(project_id, query_vec, k=20)
        steps.append(_step(
            "Vector Search", t,
            f"Query + keywords: {keywords}",
            f"{len(raw_results)} candidates",
        ))

        # Step 3: BM25 + hybrid re-rank (50% cosine + 50% BM25)
        t = _now()
        scored: list[tuple[RetrievedChunk, float]] = []
        query_tokens: list[str] = []

        if raw_results:
            corpus = [r["content"].lower().split() for r in raw_results]
            query_tokens = " ".join(keywords).lower().split() or ["_"]
            bm25 = BM25Okapi(corpus)
            bm25_raw = bm25.get_scores(query_tokens)
            bm25_max = float(max(bm25_raw)) if float(max(bm25_raw)) > 0 else 1.0
            bm25_norm = [float(s) / bm25_max for s in bm25_raw]

            for i, r in enumerate(raw_results):
                # ChromaDB cosine distance in [0,2]; convert to similarity in [0,1]
                vec_score = round(max(0.0, 1.0 - r["distance"]), 4)
                bm25_score = round(bm25_norm[i], 4)
                final_score = round(0.5 * vec_score + 0.5 * bm25_score, 4)
                content_lower = r["content"].lower()
                matched_kws = [kw for kw in keywords if kw.lower() in content_lower]
                scored.append((
                    RetrievedChunk(
                        chunk_id=r["id"],
                        filename=r["metadata"]["filename"],
                        chunk_index=r["metadata"]["chunk_index"],
                        content=r["content"],
                        score=final_score,
                        vec_score=vec_score,
                        bm25_score=bm25_score,
                        kw_hits=len(matched_kws),
                        keywords_matched=matched_kws,
                    ),
                    final_score,
                ))
            scored.sort(key=lambda x: x[1], reverse=True)

        top_score = f"{scored[0][1]:.3f}" if scored else "no results"
        steps.append(_step(
            "BM25 + Hybrid Rank", t,
            f"{len(scored)} chunks · tokens: {query_tokens}",
            f"Top score: {top_score}",
        ))

        # Step 4: Build context from the agent's configured top_k chunks
        t = _now()
        top_chunks = [rc for rc, _ in scored[: agent.top_k]]
        context_text = "\n\n---\n\n".join(
            f"[{rc.filename} chunk {rc.chunk_index}]\n{rc.content}" for rc in top_chunks
        )
        steps.append(_step(
            "Build Context", t,
            f"Top {len(top_chunks)} chunks (top_k={agent.top_k})",
            f"{len(context_text)} chars",
        ))

        # Step 5: Generate final answer using agent's system prompt
        t = _now()
        answer_resp = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{context_text}\n\nQUESTION: {question}",
                },
            ],
            temperature=0.2,
        )
        answer = answer_resp.choices[0].message.content or ""
        steps.append(_step("Generate Answer", t, question, f"{len(answer)} chars"))

    except AuthenticationError:
        raise HTTPException(401, "Invalid OpenAI API key. Check OPENAI_API_KEY in your .env.")
    except RateLimitError:
        raise HTTPException(429, "OpenAI rate limit exceeded. Try again shortly.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"RAG pipeline failed: {e}")

    # Persist the exchange only after a successful response
    await create_message(db, agent_id, "user", question)
    await create_message(db, agent_id, "assistant", answer)

    return ChatResponse(
        answer=answer,
        tool_steps=steps,
        retrieved_chunks=top_chunks,
        keywords=keywords,
    )
