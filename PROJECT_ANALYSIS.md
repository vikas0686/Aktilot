# Aktilot — Comprehensive Project Analysis

> **Generated:** 2026-07-08 | **Last verified:** 2026-07-15
> **Scope:** Full codebase analysis — architecture, implementation, tech stack, features, tests, infrastructure, and alignment with stated purpose.

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Purpose & Problem Statement](#purpose--problem-statement)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Backend Deep Dive](#backend-deep-dive)
- [Frontend Deep Dive](#frontend-deep-dive)
- [Infrastructure & DevOps](#infrastructure--devops)
- [Observability](#observability)
- [Testing](#testing)
- [Features Implemented](#features-implemented)
- [Design Decisions & Reasoning](#design-decisions--reasoning)
- [Alignment Analysis](#alignment-analysis)
- [Gaps & Improvement Opportunities](#gaps--improvement-opportunities)

---

## Executive Summary

Aktilot is a **self-hosted, open-source RAG (Retrieval-Augmented Generation) platform** that lets teams upload documents, create configurable AI agents, and chat with their knowledge base — all on their own infrastructure with no data leaving their servers.

The project is well-architected and execution-ready. It implements a full document-to-answer pipeline with hybrid retrieval (BM25 + vector search), durable workflow orchestration via Temporal, production-grade observability (53 custom metrics, 7 Grafana dashboards, distributed tracing), and a clean React frontend. The codebase shows a clear evolution from a simpler prototype to a project/agent-scoped architecture, with legacy code still present but cleanly separated from active routes.

**Maturity level:** Late prototype / early production. The core pipeline works end-to-end. Infrastructure is Docker Compose-based (appropriate for self-hosted single-node deployment). Missing pieces for full production: alerting, security hardening, E2E tests, and a deployment pipeline.

---

## Purpose & Problem Statement

**The problem Aktilot solves:**

1. Enterprise teams have documents scattered across contracts, reports, runbooks, and research papers
2. Finding answers requires manually searching files or paying for hosted AI services that ingest sensitive data
3. Building a custom RAG pipeline from scratch requires weeks of engineering work
4. Hosted solutions are expensive, opaque, and require handing data to third parties

**Aktilot's value proposition:**

- Self-hosted: documents never leave your network
- Open-source (MIT): full transparency and control
- Operational in minutes via Docker Compose
- Hybrid retrieval that outperforms pure vector search on factual questions
- Full pipeline transparency: every step is visible and traceable

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         User (Browser)                                    │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (React 19 / Vite / Nginx)                                      │
│  - Project/Agent/Chat UI                                                 │
│  - TanStack Query for state management                                   │
│  - Polling for real-time status (file processing)                        │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ /api proxy
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Backend API (FastAPI / Python 3.12)                                     │
│  - REST endpoints (projects, files, agents, chat, sessions)              │
│  - Stateless — all heavy work dispatched to Temporal                     │
│  - OpenTelemetry instrumented (traces, metrics)                          │
└──────────────┬──────────────────────────────────┬───────────────────────┘
               │ gRPC                              │ asyncpg
               ▼                                   ▼
┌──────────────────────────┐        ┌──────────────────────────────┐
│  Temporal Server         │        │  PostgreSQL 16               │
│  - Workflow orchestration │        │  - Projects, Files, Agents   │
│  - Checkpointing         │        │  - Chat sessions, Messages   │
│  - Automatic retries     │        │  - Alembic migrations        │
└──────────────┬───────────┘        └──────────────────────────────┘
               │ Task dispatch
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Temporal Worker (same Docker image, different CMD)                       │
│  ┌─────────────────────────┐  ┌────────────────────────────────────┐    │
│  │ DocumentWorkflow        │  │ ChatWorkflow                        │    │
│  │ 1. Update status        │  │ 1. Get agent config                 │    │
│  │ 2. Read & split file    │  │ 2. Extract keywords (LLM)           │    │
│  │ 3. Clear old vectors    │  │ 3. Embed query (OpenAI)             │    │
│  │ 4. Embed & index (OAI)  │  │ 4. Search vectors (ChromaDB)        │    │
│  │ 5. Update status        │  │ 5. Hybrid rank (BM25 + cosine)      │    │
│  └─────────────────────────┘  │ 6. Build context                    │    │
│                                │ 7. Generate answer (LLM)            │    │
│                                │ 8. Persist messages                  │    │
│                                └────────────────────────────────────┘    │
└──────────────┬──────────────────────────────────┬───────────────────────┘
               │                                   │
               ▼                                   ▼
┌──────────────────────────┐        ┌──────────────────────────────┐
│  OpenAI API              │        │  ChromaDB (Persistent)        │
│  - text-embedding-3-small│        │  - Per-project collections    │
│  - gpt-4o-mini           │        │  - Cosine distance HNSW      │
└──────────────────────────┘        └──────────────────────────────┘
```

**Data flows through two durable workflows:**

| Workflow | Trigger | Steps | Checkpoint Benefit |
|---|---|---|---|
| DocumentWorkflow | File upload | Read → Split → Embed → Index | Rate limit on embedding? Only that batch retries |
| ChatWorkflow | Chat message | Keywords → Embed → Search → Rank → Generate → Persist | LLM failure? Re-ranks and searches are NOT repeated |

---

## Tech Stack

### Backend
| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Framework | FastAPI | 0.115.5 | REST API with auto-generated OpenAPI docs |
| Runtime | Python | 3.12+ | Async-first with type annotations |
| Database | PostgreSQL | 16 | Relational data (projects, agents, messages) |
| ORM | SQLAlchemy | 2.0+ | Async ORM with mapped_column style |
| Migrations | Alembic | 1.13+ | Sequential schema migrations |
| Vector Store | ChromaDB | 0.5+ | Persistent embeddings with cosine HNSW |
| LLM | OpenAI | 1.58.1 | GPT-4o-mini (chat), text-embedding-3-small |
| Orchestration | Temporal | 1.7+ | Durable workflows with automatic retry |
| Ranking | rank-bm25 | 0.2.2 | Okapi BM25 keyword scoring |
| Tokenizer | tiktoken | 0.7+ | Token counting for cost estimation |
| Doc Parsing | pypdf, python-docx | 5.1, 1.2 | PDF and Word document text extraction |
| Observability | OpenTelemetry SDK | Full stack | Traces, metrics, logs via OTLP/gRPC |

### Frontend
| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Framework | React | 19.2 | UI with concurrent features |
| Build | Vite | 8 | Fast HMR + bundling |
| Language | TypeScript | 6 | Strict type-checked codebase |
| Routing | React Router | 7.18 | Client-side navigation |
| Server State | TanStack Query | 5.62 | Queries, mutations, cache invalidation |
| HTTP | Axios | 1.7.9 | API client with interceptors |
| Styling | TailwindCSS | 3.4 | Utility-first CSS |
| Components | Radix UI + CVA | Latest | Accessible headless primitives |
| Icons | Lucide React | 0.468 | Consistent icon set |
| Markdown | react-markdown + remark-gfm | 10.1 | Rich answer rendering |
| Testing | Vitest + Testing Library | 2 / 16 | Unit + integration tests |

### Infrastructure
| Component | Technology | Purpose |
|---|---|---|
| Container Runtime | Docker Compose | 10 services orchestrated |
| Reverse Proxy | Nginx | Static serving + API proxy |
| Metrics | Prometheus 2.53 | Time-series storage + queries |
| Tracing | Grafana Tempo 2.5 | Distributed trace storage |
| Dashboards | Grafana 11.1 | 7 pre-built dashboards |
| Telemetry Pipeline | OTel Collector Contrib 0.104 | Receives, processes, exports telemetry |
| CI/CD | GitHub Actions | Lint + test on push/PR |

---

## Project Structure

```
Aktilot/
├── README.md                    # Main documentation
├── CONTRIBUTING.md              # Developer guide
├── OBSERVABILITY.md             # Dashboard & metrics guide
├── LICENSE                      # MIT
├── docker-compose.yml           # 10-service stack
├── .env.example                 # Environment template
├── otel-collector-config.yaml   # Telemetry pipeline config
├── prometheus.yml               # Metrics scraping config
├── tempo.yaml                   # Trace storage config
├── .github/
│   ├── workflows/ci.yml         # CI pipeline
│   ├── pull_request_template.md
│   └── ISSUE_TEMPLATE/          # Bug + feature templates
├── grafana/provisioning/        # Dashboards + datasources
├── docs/                        # Architecture docs, blog, screenshots
├── backend/
│   ├── main.py                  # FastAPI app entry
│   ├── config.py                # Pydantic Settings
│   ├── requirements.txt         # 26 Python deps
│   ├── Dockerfile               # Production container
│   ├── api/routes/              # 5 route files (6 routers)
│   ├── db/models/               # 5 SQLAlchemy models
│   ├── models/schemas.py        # Pydantic request/response
│   ├── services/                # 7 service modules
│   ├── vectorstore/             # ChromaDB wrapper
│   ├── temporal/                # Workflows, activities, worker
│   ├── observability/           # OTel bootstrap + 53 metrics
│   ├── alembic/                 # 6 migrations
│   └── tests/                   # 9 test files (112 tests)
└── frontend/
    ├── package.json             # React 19, TanStack Query 5, Vite 8
    ├── Dockerfile               # Multi-stage (build + nginx)
    ├── nginx.conf               # SPA + API proxy
    ├── src/
    │   ├── pages/               # 8 page components (4 active + 4 legacy)
    │   ├── components/          # 7 feature components + 7 UI primitives
    │   ├── hooks/               # useApi (25 hooks) + useDarkMode
    │   ├── services/api.ts      # Axios client (8 namespaces, 22 methods)
    │   ├── types/api.ts         # 10 TypeScript interfaces
    │   └── __tests__/           # 2 test files (52 tests)
    └── vitest.config.ts         # Test configuration
```

---

## Backend Deep Dive

### Database Schema (6 tables)

```
┌──────────────┐      ┌──────────────┐      ┌──────────────────┐
│   projects   │──1:*─│    files     │      │                  │
│──────────────│      │──────────────│      │                  │
│ id (UUID PK) │      │ id (UUID PK) │      │                  │
│ name         │      │ project_id FK│      │                  │
│ description  │      │ filename     │      │                  │
│ created_at   │      │ filepath     │      │                  │
└──────┬───────┘      │ size         │      │                  │
       │              │ chunk_status │      │                  │
       │              │ chunk_count  │      │                  │
       │              │ uploaded_at  │      │                  │
       │              └──────────────┘      │                  │
       │                                    │                  │
       │ 1:*     ┌──────────────┐    1:*    │  ┌────────────┐ │
       └─────────│    agents    │───────────┼──│  messages  │ │
                 │──────────────│           │  │────────────│ │
                 │ id (UUID PK) │    1:*    │  │ id         │ │
                 │ project_id FK│───────┐   │  │ agent_id FK│ │
                 │ name         │       │   │  │ session_id │ │
                 │ description  │       │   │  │ role       │ │
                 │ system_prompt│       ▼   │  │ content    │ │
                 │ top_k        │  ┌────────┴──│ created_at │ │
                 │ created_at   │  │chat_sessions            │ │
                 └──────────────┘  │──────────────────────── │ │
                                   │ id (UUID PK)            │ │
                                   │ agent_id FK             │ │
                                   │ title                   │ │
                                   │ created_at              │ │
                                   │ updated_at              │ │
                                   └─────────────────────────┘ │
```

### API Endpoints (18 endpoints across 6 routers)

| Router | Method | Path | Purpose |
|---|---|---|---|
| Health | GET | `/api/health` | Health check (inline in main.py) |
| Projects | POST | `/api/projects` | Create project |
| | GET | `/api/projects` | List all projects |
| | GET | `/api/projects/:id` | Get project |
| | DELETE | `/api/projects/:id` | Delete (cascade) |
| Files | POST | `/api/projects/:id/files/upload` | Upload + start DocumentWorkflow |
| | GET | `/api/projects/:id/files` | List files |
| | DELETE | `/api/projects/:id/files/:fid` | Delete (disk + vector + DB) |
| Agents | POST | `/api/projects/:id/agents` | Create agent |
| | GET | `/api/projects/:id/agents` | List project agents |
| | GET | `/api/agents/:id` | Get agent |
| | PUT | `/api/agents/:id` | Update agent |
| | DELETE | `/api/agents/:id` | Delete agent |
| Chat | POST | `/api/agents/:id/chat` | Send message → ChatWorkflow |
| | GET | `/api/agents/:id/messages` | List messages (legacy) |
| Sessions | POST | `/api/agents/:id/sessions` | Create session |
| | GET | `/api/agents/:id/sessions` | List sessions |
| | GET | `/api/sessions/:id/messages` | Session messages |

### Service Layer Pattern

Routes are thin wrappers that:
1. Validate input (FastAPI/Pydantic)
2. Delegate to service functions
3. Return serialized responses

Services handle:
- Database operations via injected async sessions
- Cascade cleanup (disk + vector + DB)
- Business logic validation

### Temporal Workflows (Durable Execution)

**DocumentWorkflow** — 5 activities with differentiated retry:
- Infrastructure retries (Postgres, ChromaDB): 10 attempts, 500ms → 30s backoff
- OpenAI retries (embeddings): 10 attempts, 2s → 60s backoff
- Disk operations: 3 attempts (unlikely to self-resolve)
- Large payloads written to temp files (avoids Temporal's 4MB history limit)

**ChatWorkflow** — 8 activities forming the RAG pipeline:
- OpenAI retries: 4 attempts, 2s → 60s exponential backoff
- Infrastructure: 10 attempts, 500ms → 30s
- CPU-only (hybrid_rank): 3 attempts
- Non-retryable errors: AUTH_ERROR, NOT_FOUND (short-circuit retry)

### Hybrid Retrieval Algorithm

```
Score = 0.5 × cosine_similarity + 0.5 × normalized_bm25
```

1. **Extract Keywords** — LLM extracts search terms from the question
2. **Vector Search** — ChromaDB top-20 by cosine distance
3. **BM25 Score** — Okapi BM25 over candidate chunks using extracted keywords
4. **Normalize** — Both scores to [0,1] range
5. **Blend** — 50/50 weighted combination
6. **Sort & Slice** — Return top_k (agent-configurable, default 2)

This hybrid approach outperforms pure vector search on factual questions (dates, names, figures) where keyword overlap is a strong signal.

---

## Frontend Deep Dive

### Component Architecture

```
App (QueryClient + Router + AppShell)
├── AppShell (Header + Sidebar + Content)
│   ├── Header (Logo + Dark Mode Toggle)
│   ├── Sidebar (Project Tree + Agent Links)
│   └── Routes
│       ├── ProjectsPage (Grid of ProjectCards + CreateModal)
│       ├── ProjectDetailPage (FilesTab)
│       │   └── FilesTab (Drag-drop Upload + File Table)
│       ├── ProjectAgentsPage (AgentsTab)
│       │   └── AgentsTab (Agent Cards + Form Modal)
│       └── AgentChatPage (Chat + ChatSessionsPanel)
│           ├── Message Bubbles (UserBubble + AssistantBubble)
│           ├── SourcesSection (ToolSteps + ChunkCards)
│           └── ChatSessionsPanel (Session List + New Chat)
```

### State Management Philosophy

- **Zero client-side stores** — No Redux, Zustand, or Context for data
- **Server state** via TanStack Query: automatic caching, deduplication, background refetch
- **Smart polling**: Files tab refetches every 3s only while documents are processing
- **Optimistic UI**: Chat messages appear instantly, server response appends metadata
- **Cache invalidation**: Every mutation invalidates related queries automatically

### Key UX Patterns

| Pattern | Implementation |
|---|---|
| Real-time processing status | 3s polling while files pending/chunking |
| Pipeline transparency | Expandable ToolStep rows with timing + IO |
| Source attribution | ChunkCards with score breakdown per chunk |
| Safe deletion | Double-click confirm (click → "Delete?" → confirm) |
| Dark mode | CSS custom properties + class toggle + localStorage |
| Markdown answers | react-markdown with GFM tables/code blocks |
| Keyboard shortcuts | Enter to send, Shift+Enter for newline |

---

## Infrastructure & DevOps

### Docker Compose (10 services)

| Service | Image | Port | Role |
|---|---|---|---|
| postgres | postgres:16-alpine | 5432 | Application database |
| temporal | temporalio/auto-setup | 7233 | Workflow orchestration |
| temporal-ui | temporalio/ui | 8233 | Workflow monitoring UI |
| backend | ./backend (custom) | 8000 | FastAPI REST API |
| worker | ./backend (custom CMD) | — | Temporal activity executor |
| frontend | ./frontend (multi-stage) | 3000 | Nginx + React SPA |
| otel-collector | otel/collector-contrib:0.104 | 4317/8889 | Telemetry pipeline |
| prometheus | prom/prometheus:2.53 | 9090 | Metrics storage |
| tempo | grafana/tempo:2.5 | 3200 | Trace storage |
| grafana | grafana/grafana:11.1 | 3002 | Dashboards |

**Design decisions:**
- Worker shares Docker image with backend (different CMD) — efficient, consistent deps
- Named volumes for all persistent state (DB, uploads, vectors, metrics, traces)
- Health checks with `depends_on: condition` for startup ordering
- Backend runs `alembic upgrade head` on container start (auto-migration)

### CI/CD (GitHub Actions)

```yaml
Triggers: push to main, PR to main
Jobs:
  Backend:  Python 3.12 → pip install → ruff check → ruff format --check → pytest
  Frontend: Node 20 → npm ci → npm run build (type-check) → npm test
```

- Backend tests run against in-memory SQLite (no external deps needed)
- Frontend build step doubles as TypeScript type verification
- Proper caching for pip and npm

---

## Observability

### Three Pillars Implemented

| Pillar | Implementation | Storage | Visualization |
|---|---|---|---|
| Metrics | 53 custom OTel instruments | Prometheus (15d retention) | 7 Grafana dashboards |
| Traces | Auto-instrumented (FastAPI, SQLAlchemy, HTTPX) + custom spans | Grafana Tempo (7d) | Explore view + exemplars |
| Logs | OTel log exporter | Debug (collector stdout) | — |

### Custom Metrics (53 instruments across 8 categories)

1. **Retrieval** — vector search latency, BM25 latency, hybrid latency, top_k stats, score distributions
2. **Reranker** — latency, docs in/out/discarded, score averages
3. **Prompt** — build latency, token breakdowns (system/question/context), chunks included
4. **LLM** — request latency, input/output/total tokens, tokens/sec, finish reason
5. **Embedding** — latency, tokens, batch size, dimension gauge
6. **Vector Database** — search/insert latency, collection size gauge, query/insert counters
7. **Workflow** — duration, activity duration, queue delay, retries, failures
8. **Token/Cost** — cumulative input/output/embedding tokens by model and purpose

### 7 Pre-Built Dashboards

| # | Dashboard | Key Question It Answers |
|---|---|---|
| 1 | RAG Pipeline Overview | Is the system healthy right now? |
| 2 | Retrieval Quality | Are answers relevant? Is retrieval finding good chunks? |
| 3 | Prompt Intelligence | Where are tokens being spent? Is context growing? |
| 4 | LLM Performance | Are LLM calls slow? Are answers being truncated? |
| 5 | Vector DB Health | Are documents indexed? Is ChromaDB performing? |
| 6 | Token & Cost Intelligence | What's the per-model, per-purpose token spend? |
| 7 | Temporal Workflows | Are workflows failing or backing up? |

### Trace Correlation

- Metric panels link to traces via exemplar support (Prometheus + Tempo)
- Traces span from HTTP request → Temporal workflow → individual activities
- Service map auto-generated from span metrics (Tempo metrics_generator)

---

## Testing

### Backend (pytest — 112 tests, 9 files)

| Test File | Tests | Coverage Area |
|---|---|---|
| test_health.py | 1 | API smoke test |
| test_projects.py | 11 | Project CRUD + cascade delete |
| test_agents.py | 13 | Agent CRUD + project scoping + validation |
| test_files.py | 11 | Upload validation + Temporal workflow trigger |
| test_chat.py | 16 | Chat flow + sessions + error propagation (Temporal→HTTP) |
| test_chat_activities.py | 18 | Temporal activity units (keywords, embed, rank, generate) |
| test_chunk_service.py | 16 | Text splitting + file parsing (PDF, DOCX, TXT) |
| test_rag_service.py | 15 | Legacy RAG service end-to-end |
| test_schemas.py | 11 | Pydantic schema validation |

**Testing strategy:**
- External services mocked: OpenAI (patched), ChromaDB (sys.modules mock), Temporal (mock client)
- Database: Real queries against in-memory SQLite (aiosqlite)
- Temporal activities: `ActivityEnvironment` from temporalio.testing
- Error chains: Full `WorkflowFailureError → ActivityError → ApplicationError → HTTP status` tested

### Frontend (Vitest — 52 tests, 2 files)

| Test File | Tests | Coverage Area |
|---|---|---|
| api.test.ts | 17 | API service layer (URL + payload correctness) |
| useApi.test.tsx | 35 | TanStack Query hooks (fetch, mutate, cache, poll) |

**Testing strategy:**
- Axios mocked at module level
- Fresh QueryClient per test (no cache bleed)
- Shared QueryClient tests for cache invalidation verification
- Fake timers for polling behavior (3s file status refresh)

### Test Quality Assessment

**Strengths:**
- Covers happy paths AND edge cases thoroughly
- Tests mathematical formulas (hybrid scoring: 0.5*vec + 0.5*bm25)
- Tests error classification (retryable vs non-retryable)
- Tests cascade behaviors (delete project → removes agents → removes messages)
- Tests cache invalidation chains in React Query

**Gaps:**
- No React component rendering tests (pages, forms, interactions)
- No E2E tests (Playwright/Cypress)
- No document_activities unit tests (read_and_split_file, embed_and_index_chunks)
- No Temporal integration tests (using test server)
- No accessibility tests
- No coverage thresholds enforced in CI

---

## Features Implemented

### Core Features (Working)

| Feature | Status | Implementation |
|---|---|---|
| Project-based document organization | ✅ Complete | Per-project ChromaDB collections + upload dirs |
| Multi-format document upload | ✅ Complete | PDF (pypdf), Word (python-docx), plain text |
| Chunking with overlap | ✅ Complete | 1000 chars, 200 overlap — fixed-size |
| OpenAI embedding generation | ✅ Complete | text-embedding-3-small, batched (100) |
| Hybrid BM25 + vector retrieval | ✅ Complete | 50/50 blend, top-20 candidates → top_k results |
| Configurable AI agents | ✅ Complete | Custom system prompts, persona, top_k per agent |
| Multi-session chat | ✅ Complete | Sessions with auto-title from first question (note: prior messages not included in LLM context) |
| Source attribution | ✅ Complete | Chunk content, filename, position, score breakdown |
| Pipeline transparency | ✅ Complete | Every step: name, timing, input/output summary |
| Durable document processing | ✅ Complete | Temporal DocumentWorkflow with checkpointing |
| Durable chat pipeline | ✅ Complete | Temporal ChatWorkflow with per-step retry |
| Live processing status | ✅ Complete | 3s polling on pending/chunking files |
| Full observability stack | ✅ Complete | 53 metrics, 7 dashboards, distributed tracing |
| Dark mode | ✅ Complete | CSS custom properties + localStorage |
| Self-hosted via Docker | ✅ Complete | Single `docker compose up` starts everything |

### Planned Features (Not Yet Implemented)

| Feature | Status | Evidence |
|---|---|---|
| BenchmarkWorkflow | 🔜 Mentioned in README | Recall@K, MRR, latency evaluation |
| Agentic RAG (ReAct loop) | 📐 Designed | Full architecture doc in `docs/AGENTIC_RAG_ARCHITECTURE.md` |
| Cross-encoder reranking | 📐 Designed | Mentioned in architecture doc (currently using score-based) |
| Memory layer (long-term prefs) | 📐 Designed | Architecture doc describes it |
| File streaming/WebSocket updates | Not started | Currently uses polling |

---

## Design Decisions & Reasoning

### 1. Temporal for Workflow Orchestration

**Why:** Document processing and RAG pipelines are multi-step, failure-prone operations. A naive approach loses work on failure and wastes API credits on retries.

**Benefit:** Each activity is checkpointed. If OpenAI rate-limits at step 4, only step 4 retries — steps 1-3 are replayed from history at zero cost. The user never sees a stuck upload.

**Trade-off:** Adds infrastructure complexity (Temporal server + worker process). Justified by the reliability gains for a system that calls external APIs with rate limits and costs per call.

### 2. Hybrid BM25 + Vector Retrieval

**Why:** Pure vector search excels at semantic similarity but struggles with precise factual queries (dates, names, contract numbers). BM25 captures exact keyword matches that embeddings may miss.

**Benefit:** 50/50 blend consistently outperforms either method alone on factual questions while maintaining semantic understanding.

**Trade-off:** Slightly more computation per query (BM25 scoring over candidate set). Negligible compared to LLM latency.

### 3. ChromaDB (not FAISS, Pinecone, or pgvector)

**Why:** Persistent, zero-config, runs in-process or on disk. No external service needed. Per-project collection isolation is natural.

**Trade-off:** Not horizontally scalable (single-node). Appropriate for the self-hosted single-team use case. The architecture doc acknowledges a future path to Pinecone/Weaviate for scale.

### 4. TanStack Query (not Redux/Zustand)

**Why:** All frontend state is server state (projects, files, agents, messages). TanStack Query provides caching, deduplication, background refresh, and mutation invalidation — exactly what's needed. No client-only state complex enough to warrant a separate store.

**Benefit:** Zero boilerplate store code. Automatic stale-while-revalidate. Smart polling for file processing status.

### 5. Fixed-Size Chunking (1000 chars, 200 overlap)

**Why:** Simple, predictable, and effective. Semantic or recursive chunking adds complexity without guaranteed quality improvement for the target use cases (contracts, runbooks, reports with clear section boundaries).

**Trade-off:** May split mid-sentence. The 200-char overlap mitigates this by ensuring context continuity across chunk boundaries.

### 6. Stateless API + Worker Separation

**Why:** The API server handles HTTP requests and dispatches work. The worker handles CPU/IO-intensive operations (embedding, LLM calls, vector indexing). This separation means:
- API can scale independently (horizontal)
- Worker crashes don't lose progress (Temporal durability)
- No background thread management in the API process

### 7. Per-Project Isolation (Collections + Upload Dirs)

**Why:** Legal, compliance, and organizational reasons demand that project A's documents never appear in project B's results. Separate ChromaDB collections provide hard isolation at the retrieval layer.

---

## Alignment Analysis

### Does the implementation align with the stated purpose?

| Stated Goal | Implementation | Alignment |
|---|---|---|
| "Chat with your documents" | Full RAG pipeline: upload → chunk → embed → retrieve → generate | ✅ Fully aligned |
| "On your infrastructure" | Docker Compose, all data in local volumes, no external services except OpenAI | ✅ Fully aligned |
| "No data leaves your servers" | Documents stored locally, vectors in local ChromaDB. Only queries go to OpenAI | ⚠️ Mostly aligned — queries+chunks sent to OpenAI for generation |
| "Minutes, not weeks" | Single `docker compose up --build` | ✅ Fully aligned |
| "Isolated vector stores per project" | Per-project ChromaDB collections | ✅ Fully aligned |
| "Configurable agents" | System prompt, top_k, per-agent settings | ✅ Fully aligned |
| "Answers with sources" | Every response includes ranked chunks with scores | ✅ Fully aligned |
| "See every step of the pipeline" | ToolSteps with timing + IO for each activity | ✅ Fully aligned |
| "Resilient by design" | Temporal workflows with checkpointing + differentiated retries | ✅ Fully aligned |
| "Hybrid BM25 + vector" | 50/50 blend implemented in hybrid_rank activity | ✅ Fully aligned |

**Overall alignment: STRONG.** The implementation delivers on every stated promise. The one caveat is that document content (as context chunks) is sent to OpenAI for answer generation — this is inherent to using a hosted LLM and is clearly documented. The data-at-rest never leaves the user's infrastructure.

### Architecture Maturity vs. Documentation Claims

The `AGENTIC_RAG_ARCHITECTURE.md` describes a more advanced system (ReAct agent loop, tool registry, multi-tool orchestration). The current implementation is at **Level 2 (Pipeline RAG)** — a fixed sequence of retrieval + generation steps. This is correctly acknowledged in the architecture doc as the current state, with the agentic layer as a future evolution.

---

## Gaps & Improvement Opportunities

### Security

| Gap | Risk | Recommendation |
|---|---|---|
| No authentication/authorization | Anyone with network access can read all data | Add auth layer (API keys, OAuth, or session-based) |
| Docker containers run as root | Container escape → host root | Add `USER nonroot` in Dockerfiles |
| No nginx security headers | XSS, clickjacking, MIME sniffing | Add CSP, HSTS, X-Frame-Options, X-Content-Type-Options |
| CORS allow_origins=["*"] | Cross-origin attacks in non-isolated deployments | Restrict to frontend origin |
| SECURITY.md referenced but doesn't exist | Confusion for reporters | Create the file |
| No input sanitization on system prompts | Prompt injection via agent config | Document the risk; consider guardrails |

### Testing

| Gap | Impact | Recommendation |
|---|---|---|
| No component tests | UI regressions undetected | Add React Testing Library tests for key pages |
| No E2E tests | Integration issues between frontend + backend | Add Playwright smoke tests |
| No document_activities tests | Embedding/indexing logic untested in isolation | Add unit tests with mocked OpenAI |
| No coverage thresholds | Quality can silently regress | Enforce ≥80% in CI |
| No Temporal integration tests | Workflow orchestration untested | Use temporalio test server |

### Production Readiness

| Gap | Impact | Recommendation |
|---|---|---|
| No alerting rules | Silent failures in production | Add Prometheus alerting (Alertmanager) |
| No resource limits in Docker Compose | OOM/CPU starvation | Add `deploy.resources.limits` |
| No health checks for backend/worker | Unhealthy containers stay in rotation | Add HTTP health checks + Temporal heartbeats |
| No deployment pipeline | Manual deploys | Add CD step (image push + deploy) |
| No backup strategy | Data loss risk | Document pg_dump + volume backup procedures |
| No rate limiting on API | DoS risk, API cost exposure | Add rate limiting middleware |
| Single worker instance | No horizontal scaling | Document scaling approach (multiple workers) |

### Code Quality

| Gap | Impact | Recommendation |
|---|---|---|
| Legacy pages not removed | Codebase confusion | Delete unused UploadPage, FilesPage, ChunkPage, ChatPage, Layout |
| Legacy hooks in useApi.ts | Dead code | Remove `useFiles`, `useChunkFile`, `useChunkStats`, `useSendMessage` |
| Legacy api.ts namespaces | Dead code | Remove `filesApi`, `chunksApi`, `chatApi` |
| `context_dir` setting + `context_data` volume | Configured but unused anywhere in app code | Remove or implement |
| No API versioning | Breaking changes affect clients | Consider `/api/v1/` prefix |
| App.css is unused template CSS | Confusion | Delete it |
| No lazy loading / code splitting | Larger initial bundle | Add `React.lazy()` for page components |

### Feature Gaps

| Feature | Value | Effort |
|---|---|---|
| Conversation history in prompts | Multi-turn chat is currently contextless — prior messages not sent to LLM | Low |
| WebSocket for real-time status | Better UX than polling | Medium |
| File re-upload (re-index) | Allows document updates | Low (workflow supports it) |
| Search across projects | Cross-project knowledge queries | Medium |
| User management / multi-tenancy | Team collaboration | High |
| Local LLM support (Ollama) | True air-gapped deployment | Medium |
| Streaming responses | Better perceived latency | Medium (SSE from Temporal) |
| Chunk size configuration | Per-project tuning | Low |
| Export conversations | Audit trail | Low |

---

## Summary

Aktilot is a well-engineered, purpose-built RAG platform that delivers on its promise: upload documents, ask questions, get sourced answers — self-hosted with full pipeline transparency. The architecture choices (Temporal for durability, hybrid retrieval for accuracy, per-project isolation, extensive observability) are well-reasoned and appropriate for the problem domain.

The codebase is clean, well-documented, and tested where it matters most (API contracts, retrieval logic, error propagation). The observability stack is production-grade and notably sophisticated for a project at this stage. The main gaps are around security (no auth), production hardening (no resource limits, no alerting), and test coverage for the UI layer.

**Recommended next priorities:**
1. Add authentication (even basic API key auth)
2. Create SECURITY.md and fix nginx security headers
3. Remove legacy dead code (cleaner codebase for contributors)
4. Add component tests for AgentChatPage (highest-value UI)
5. Add coverage thresholds to CI
6. Implement streaming responses (significant UX improvement)
