import json
from datetime import datetime, timezone

from fastapi import HTTPException
from openai import AsyncOpenAI, AuthenticationError, RateLimitError

from config import settings
from models.schemas import ChatResponse, RetrievedChunk, ToolStep
from vectorstore.faiss_store import vector_store

client = AsyncOpenAI(api_key=settings.openai_api_key)

_tool_history: list[list[ToolStep]] = []
MAX_HISTORY = 100


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def chat(question: str) -> ChatResponse:
    steps: list[ToolStep] = []

    try:
        # Step 1: Extract keywords
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

        # Step 2: Search chunks (hybrid: keyword + vector similarity)
        t = _now()
        embed_resp = await client.embeddings.create(model=settings.embedding_model, input=question)
        query_vec = embed_resp.data[0].embedding
        vector_results = vector_store.search(query_vec, k=20)

        scored: list[tuple[RetrievedChunk, float]] = []
        for chunk, vec_score in vector_results:
            content_lower = chunk.content.lower()
            kw_hits = sum(1 for kw in keywords if kw.lower() in content_lower)
            kw_score = kw_hits / max(len(keywords), 1)
            final_score = 0.5 * vec_score + 0.5 * kw_score
            scored.append((
                RetrievedChunk(
                    chunk_id=chunk.id,
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    score=round(final_score, 4),
                ),
                final_score,
            ))
        steps.append(_step("Search Chunks", t, f"Query vec + keywords: {keywords}", f"{len(scored)} candidates"))

        # Step 3: Rank chunks
        t = _now()
        scored.sort(key=lambda x: x[1], reverse=True)
        steps.append(_step("Rank Chunks", t, f"{len(scored)} chunks", "Sorted by hybrid score"))

        # Step 4: Build context
        t = _now()
        top3 = [rc for rc, _ in scored[:3]]
        context_text = "\n\n---\n\n".join(
            f"[{rc.filename} chunk {rc.chunk_index}]\n{rc.content}" for rc in top3
        )
        steps.append(_step("Build Context", t, f"Top {len(top3)} chunks", f"{len(context_text)} chars of context"))

        # Step 5: Generate final response
        t = _now()
        answer_resp = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a document assistant. Use only the supplied context to answer. "
                        "If the answer is not in the context say: "
                        "'I could not find that information in the uploaded documents.'"
                    ),
                },
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{context_text}\n\nQUESTION: {question}",
                },
            ],
            temperature=0.2,
        )
        answer = answer_resp.choices[0].message.content or ""
        steps.append(_step("Generate Final Response", t, question, f"{len(answer)} chars"))

    except AuthenticationError:
        raise HTTPException(401, "Invalid OpenAI API key. Check OPENAI_API_KEY in your .env file.")
    except RateLimitError:
        raise HTTPException(429, "OpenAI rate limit exceeded. Try again shortly.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"RAG pipeline failed: {e}")

    _tool_history.append(steps)
    if len(_tool_history) > MAX_HISTORY:
        _tool_history.pop(0)

    return ChatResponse(answer=answer, tool_steps=steps, retrieved_chunks=top3)


def get_tool_history() -> list[list[ToolStep]]:
    return _tool_history
