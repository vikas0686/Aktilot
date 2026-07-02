"""
ChatWorkflow — durable, individually-retryable RAG chat pipeline.

Each step is checkpointed in Temporal history. If generate_answer fails after
extract_keywords and embed_query already succeeded, only generate_answer retries —
the two earlier OpenAI calls are not repeated.

Pipeline:
  1. get_agent_config       — Postgres read, non-retryable NOT_FOUND
  2. extract_keywords       — OpenAI call 1, retried up to 4×
  3. embed_query            — OpenAI call 2, retried up to 4×
  4. search_vectors         — ChromaDB, retried up to 10×
  5. hybrid_rank            — CPU only, retried up to 3×
  6. (build context)        — deterministic string assembly, in-workflow
  7. generate_answer        — OpenAI call 3, retried up to 4×
  8. persist_messages       — Postgres write, retried up to 10×
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.chat_activities import (
        embed_query,
        extract_keywords,
        generate_answer,
        get_agent_config,
        hybrid_rank,
        persist_messages,
        search_vectors,
    )

TASK_QUEUE = "aktilot-queue"

_OPENAI_RETRY = RetryPolicy(
    maximum_attempts=4,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
)

_INFRA_RETRY = RetryPolicy(
    maximum_attempts=10,
    initial_interval=timedelta(milliseconds=500),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
)


def _make_step(name: str, t_start, inp: str, out: str) -> dict:
    t_end = workflow.now()
    return {
        "name": name,
        "start_time": t_start.isoformat(),
        "end_time": t_end.isoformat(),
        "duration_ms": (t_end - t_start).total_seconds() * 1000,
        "input_summary": inp,
        "output_summary": out,
    }


@workflow.defn
class ChatWorkflow:
    @workflow.run
    async def run(self, agent_id: str, session_id: str, question: str) -> dict:
        config: dict = await workflow.execute_activity(
            get_agent_config,
            args=[agent_id],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=_INFRA_RETRY,
        )

        steps: list[dict] = []

        # Step 1: Extract keywords — checkpointed; if step 2+ fails, step 1 is NOT re-run
        t = workflow.now()
        keywords: list[str] = await workflow.execute_activity(
            extract_keywords,
            args=[question],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_OPENAI_RETRY,
        )
        steps.append(
            _make_step("Extract Keywords", t, question, f"Keywords: {keywords}")
        )

        # Steps 2+3: Embed then search — combined into "Vector Search" step for UI parity
        t = workflow.now()
        query_vector: list[float] = await workflow.execute_activity(
            embed_query,
            args=[question],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_OPENAI_RETRY,
        )

        raw_results: list[dict] = await workflow.execute_activity(
            search_vectors,
            args=[config["project_id"], query_vector, keywords],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=_INFRA_RETRY,
        )
        steps.append(
            _make_step(
                "Vector Search",
                t,
                f"Query + keywords: {keywords}",
                f"{len(raw_results)} candidates",
            )
        )

        # Step 4: BM25 + hybrid re-rank
        t = workflow.now()
        ranked: list[dict] = await workflow.execute_activity(
            hybrid_rank,
            args=[raw_results, keywords, config["top_k"]],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        top_score = f"{ranked[0]['score']:.3f}" if ranked else "no results"
        steps.append(
            _make_step(
                "BM25 + Hybrid Rank",
                t,
                f"{len(raw_results)} chunks",
                f"Top score: {top_score}",
            )
        )

        # Build context — pure string assembly, deterministic, no activity needed
        t_ctx = workflow.now()
        context = "\n\n---\n\n".join(
            f"[{c['filename']} chunk {c['chunk_index']}]\n{c['content']}"
            for c in ranked
        )
        steps.append(
            {
                "name": "Build Context",
                "start_time": t_ctx.isoformat(),
                "end_time": t_ctx.isoformat(),
                "duration_ms": 0,
                "input_summary": f"Top {len(ranked)} chunks",
                "output_summary": f"{len(context)} chars",
            }
        )

        # Step 5: Generate answer — checkpointed; only this retries on OpenAI failure
        t = workflow.now()
        answer: str = await workflow.execute_activity(
            generate_answer,
            args=[question, context, config["system_prompt"], len(ranked)],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_OPENAI_RETRY,
        )
        steps.append(_make_step("Generate Answer", t, question, f"{len(answer)} chars"))

        # Step 6: Persist messages — runs only after a successful answer
        await workflow.execute_activity(
            persist_messages,
            args=[agent_id, session_id, question, answer],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=_INFRA_RETRY,
        )

        return {
            "answer": answer,
            "keywords": keywords,
            "chunks": ranked,
            "steps": steps,
        }
