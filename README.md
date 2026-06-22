<div align="center">

# Aktilot

**Chat with your documents. On your infrastructure. No data leaves your servers.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

## The Problem

Your team has documents everywhere — contracts, reports, runbooks, research papers — and finding answers means either manually digging through files or paying for a hosted AI service that ingests your sensitive data.

Hosted document AI tools are expensive, opaque, and require you to hand over your files to a third party. Building your own RAG pipeline from scratch means weeks of engineering work just to get a working prototype.

**Aktilot fills that gap.** It's a self-hosted, open-source platform that lets you upload your documents and ask questions in plain English — in minutes, not weeks, with your data staying exactly where it is.

---

## What Aktilot Does

- **Organize documents into projects** — separate knowledge bases for different teams, clients, or use cases
- **Create AI agents per project** — each agent gets its own persona and instructions so it answers in the right tone and scope
- **Ask questions, get cited answers** — every response shows exactly which document chunks it drew from, so you can verify the source
- **See inside the pipeline** — keyword extraction, vector search, re-ranking, and context assembly are all surfaced in the UI with timings, so nothing is a black box
- **Resilient document processing** — uploads are processed through a durable workflow engine; if embedding fails mid-way due to a rate limit or restart, only the failed step retries — no wasted API calls or lost work

> Aktilot uses a hybrid BM25 + vector retrieval approach that consistently outperforms pure semantic search on precise factual questions.

---

## Screenshots

> *(coming soon)*

---

## Getting Started

The fastest way to run Aktilot is with Docker Compose. You need an [OpenAI API key](https://platform.openai.com/api-keys) and Docker installed.

```bash
git clone https://github.com/your-org/aktilot.git
cd aktilot

cp .env.example .env
# Open .env and set: OPENAI_API_KEY=sk-...

docker compose up --build
```

| Service | URL |
|---|---|
| App | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Temporal UI | http://localhost:8233 |

That's it. Create a project, upload a PDF, create an agent, and start asking questions.

The Temporal UI at `:8233` lets you monitor document processing jobs, inspect individual pipeline steps, and retry failed uploads without re-uploading the file.

---

## Local Development

**Prerequisites:** Python 3.12+, Node 20+, Docker (for Postgres + Temporal)

**Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set OPENAI_API_KEY and DATABASE_URL

# Start Postgres and Temporal via Docker
docker compose up postgres temporal -d

alembic upgrade head

# Terminal 1 — API server
uvicorn main:app --reload --port 8000

# Terminal 2 — Temporal worker (processes document uploads)
python -m temporal.worker
```

**Frontend**

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

**Tests**

```bash
# Backend
cd backend && source .venv/bin/activate
pytest --tb=short -q

# Frontend
cd frontend && npm test
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg) |
| `TEMPORAL_ADDRESS` | No | Temporal server address (default: `localhost:7233`) |
| `CHAT_MODEL` | No | Chat model to use (default: `gpt-4o-mini`) |
| `EMBEDDING_MODEL` | No | Embedding model (default: `text-embedding-3-small`) |
| `UPLOAD_DIR` | No | Where uploaded files are stored (default: `uploads`) |
| `CHROMA_DIR` | No | Where vector data is persisted (default: `chroma_data`) |

Copy `.env.example` to `.env` in the project root (for Docker) or `backend/.env` (for local dev).

---

## How It Works

![Aktilot Architecture](docs/aktilot-01-03.png)

All three workflows run on a **Temporal Cluster** for durable, individually-retryable execution:

- **DocumentWorkflow** — chunks, embeds, and indexes uploaded files into ChromaDB. Metadata is stored in Postgres.
- **ChatWorkflow** — hybrid BM25 + vector retrieval, LLM answer generation, and conversation persistence. Each step is checkpointed; a failed OpenAI call retries alone without re-running earlier steps.
- **BenchmarkWorkflow** *(coming soon)* — evaluates retrieval quality with Recall@K, MRR, and latency metrics, storing results in an evaluation DB.

---

## Contributing

We welcome contributions of all kinds — bug fixes, new features, documentation improvements, and feedback.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up your dev environment, our branching workflow, code standards, and how to submit a pull request.

If you've found a bug, open an [issue](https://github.com/your-org/aktilot/issues). If you have a feature idea, start a [discussion](https://github.com/your-org/aktilot/discussions) before writing code.

For security vulnerabilities, please do not open a public issue — see [SECURITY.md](SECURITY.md).

---

## License

[MIT](LICENSE) © Vikas Pandey
