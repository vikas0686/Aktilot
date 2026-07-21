# Why AI Pipelines Need Workflow-Level Observability

Your API is returning 200s. Latency is nominal. CPU is fine. Uptime is 99.9%.

And your RAG pipeline is still hallucinating, because the retriever quietly started returning irrelevant chunks three days ago, and nothing in your monitoring stack noticed — because nothing was watching for it.

This is the blind spot most teams hit the first time they put an LLM pipeline into production: the tools that tell you a system is *up* have almost nothing to say about whether it's *right*. AI pipelines fail differently than traditional web services, and they need a different layer of observability to match — one that looks inside the workflow, not just around it.

We ran into this building [Aktilot](https://github.com/aktilot), an open-source RAG platform, and ended up instrumenting every stage of the pipeline with OpenTelemetry rather than just the API boundary. This post is about why request-level monitoring isn't enough for AI systems, and what workflow-level observability actually looks like in practice.

---

## The problem: a healthy request can still be a wrong answer

A typical RAG chat request in Aktilot isn't one operation — it's a workflow made of seven distinct steps, orchestrated by Temporal: retrieve candidates, score them with BM25, blend and rerank, build a prompt, call the LLM, and so on. A dashboard that only tracks the HTTP request boundary sees exactly one thing: "the request completed in 1.2 seconds and returned 200." It has no idea which of those seven internal steps did the work, which one was slow, or whether the *content* flowing through the pipeline was any good.

That's the core failure mode of request-level monitoring applied to AI systems: it collapses a multi-stage pipeline into a single pass/fail bit. Traditional APM was built for that model — a request comes in, a handful of DB calls happen, a response goes out, and if it's slow you profile the query. AI pipelines break that model because:

- **Failure isn't binary.** A bad answer isn't an exception. Nothing throws when the retriever returns mediocre chunks — the pipeline happily generates a confident, wrong answer and returns 200.
- **The pipeline has more stages, and each one can degrade independently.** Retrieval quality, reranking, prompt assembly, and generation are separate concerns with separate failure modes.
- **Cost and latency are workflow properties, not request properties.** A slow request could mean a slow LLM call, or it could mean the request sat in a worker queue for two seconds before anyone even started working on it — and those require completely different fixes.

Workflow-level observability means instrumenting each stage of the pipeline as a first-class citizen, so you can answer "which step, exactly, is the problem" instead of just "was the request slow."

---

## What this looks like in practice

We instrumented Aktilot's full pipeline — ingestion, retrieval, reranking, prompt assembly, LLM calls, vector DB operations, and the Temporal workflow layer itself — with OpenTelemetry, exported through an OTEL Collector into Prometheus (metrics) and Tempo (traces), visualized in Grafana. Here's what fell out of doing that properly, and why each piece matters.

### 1. Stage-level latency, not just request latency

The obvious first step is breaking total latency down by stage. Aktilot emits `rag.workflow.activity_duration_ms`, labeled by activity type, specifically because workflow-level latency alone can't tell you whether `generate_answer` (the LLM call) or `hybrid_rank` (BM25 + reranking) is the actual bottleneck. In practice, the LLM call dominates almost every time — but you only know that because you measured it, not because you assumed it.

This sounds trivial, but it's the difference between "the chat endpoint is slow, no idea why" and "72% of latency is one specific activity, here's the histogram."

### 2. Quality signals that are completely orthogonal to error signals

This is the part classic monitoring can't see at all. A retriever returning garbage doesn't error — it just quietly makes the whole system worse. You need metrics whose entire purpose is to measure *quality*, independent of whether anything crashed.

Aktilot tracks:
- `rag.reranker.score_top1` — the hybrid score of the best-ranked chunk returned. This is treated as the primary retrieval-quality signal. A top-1 score dropping below ~0.4 means retrieval isn't finding relevant content anymore — with zero errors thrown anywhere.
- `rag.retrieval.score_avg`, split by `score_type` (vector / BM25 / hybrid) — lets you catch cases where the hybrid blend is *worse* than vector search alone, meaning BM25 is actively hurting results.
- `rag.reranker.docs_discarded` — at k=20 → top_k=6, the expected discard ratio is roughly 0.7. When that ratio drifts, it's a signal that the candidate pool composition changed, even though nothing "broke."

None of these are health checks. They're baselines with expected ranges, and the interesting alert isn't "value is null" — it's "value moved away from its historical band."

### 3. Paired counters as a cheap correctness check

One of the more useful patterns we landed on: instrumenting two counters that *should* move in lockstep, and watching for divergence. Aktilot's chat workflow calls the LLM for two purposes — `generate_answer` and `keyword_extract` — and under normal operation, `rag.llm.requests_total` for each purpose should track roughly 1:1. If `keyword_extract` calls start falling behind `generate_answer` calls, it means a workflow step is silently failing (swallowed exception, early return, whatever) without ever surfacing as an error metric.

This is cheap to build and catches a whole category of bug that error-rate dashboards structurally can't — the silent partial failure.

### 4. Cost attribution by stage, not a monthly total

"We spent $4,200 on OpenAI this month" tells you nothing actionable. Workflow-level observability means attributing cost to the specific stage and reason it was incurred:

- `rag.prompt.tokens_context` vs `tokens_system` vs `tokens_user_question`, tracked as a stacked breakdown per query. Rising context tokens means your chunking or `top_k` needs tuning. Rising system tokens means your prompt template is bloating — and that cost compounds on *every single query*, so it's worth catching early.
- `rag.tokens.embedding_total`, split by call site (ingestion vs. query time). Ingestion spend is expected to be bursty — it spikes on document upload. Query-time embedding spend growing steadily is a usage trend, and conflating the two in one aggregate number hides both signals.

Once cost is broken down this way, "reduce spend" turns into a specific, actionable target instead of a vague budget conversation.

### 5. Retry and failure attribution at the activity level

A workflow-level "5% failure rate" is nearly useless when you're on call at 2am. What you actually need is: *which* activity, *which* dependency, and *is this something that will self-heal or does it need a human*.

Aktilot's `rag.workflow.retries_total` and `rag.workflow.activity_failures_total` are labeled per activity type, so a spike immediately tells you whether OpenAI, ChromaDB, or Postgres is the flaky one. The failure counter also carries a `non_retryable` label — `non_retryable=true` means it's an auth or config error that will keep failing until someone intervenes, versus a transient error that Temporal's retry policy will absorb on its own. That one label is the difference between paging someone and letting the system heal itself.

### 6. Distinguishing "slow" from "backed up"

Rising latency has two very different root causes: the work itself got slower, or requests are sitting in a queue waiting for a free worker. These require completely different fixes — optimizing a prompt versus scaling out workers — and request-level latency alone can't tell them apart.

Because Aktilot's workflow layer runs on Temporal, this distinction comes almost for free: `rag.workflow.queue_delay_ms` measures time between an activity being scheduled and a worker actually picking it up, while `rag.workflow.activity_duration_ms` measures actual execution time. Add `temporal_worker_task_slots_available` (visibility into worker saturation) and you can tell at a glance whether you're LLM-bound or worker-bound — two problems that look identical from the outside but have opposite fixes.

### 7. Traces to connect the dots on a single bad request

Aggregate dashboards tell you the system trend. When a specific user reports "this answer was wrong," you need to go from that one complaint to the exact retrieval scores, token counts, and activity timings for *that specific request* — not just the aggregate.

Every API request and workflow activity in Aktilot is traced end-to-end through Grafana Tempo, linking the HTTP request → workflow execution → individual activity spans. That means a support engineer can pull the trace ID for one user's bad answer and see precisely which chunks were retrieved, what their scores were, and how many tokens went into the prompt — turning "the AI was wrong" into a debuggable, specific incident.

---

## A framework you can apply beyond RAG

None of this is specific to RAG pipelines — the same reasoning applies to any multi-stage LLM system (agents, multi-step tool-calling pipelines, extraction workflows). The pattern generalizes to a short checklist:

1. **Instrument every pipeline stage independently**, not just the request boundary. If your workflow has N steps, you should be able to see latency and volume for each of the N, not just the sum.
2. **Track quality metrics as a category separate from health metrics.** A 200 status code and a good answer are different guarantees, and only one of them is covered by traditional monitoring.
3. **Instrument paired counters that should move together** as a cheap, free correctness check for silent partial failures.
4. **Attribute cost to stage and purpose**, not just an aggregate bill — cost breakdowns should be actionable, not just informative.
5. **Label retries and failures by the specific dependency**, and distinguish retryable from non-retryable — that's what turns a metric into an actionable page.
6. **Separate queue delay from execution time** so you can tell saturation from slowness before you scale the wrong thing.
7. **Trace individual requests end-to-end** so aggregate dashboards can be backed up by per-request forensics when something specific goes wrong.

## Closing thought

The uncomfortable truth about AI pipelines is that "it's not throwing errors" and "it's working correctly" are much further apart than they are for traditional software. Uptime monitoring was built for a world where correctness and availability were roughly the same problem. In AI pipelines, they're not — and the gap between them is exactly where workflow-level observability has to live.

If you want to see the full instrumented stack — dashboards, metric definitions, and the OTel/Temporal wiring — it's all open source in [Aktilot's observability docs](OBSERVABILITY.md).
