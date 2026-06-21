<div align="center">

# Aktilot

**Chat with your documents. On your infrastructure. No data leaves your servers.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

## The Problem

Your team has documents everywhere — contracts, reports, runbooks, research papers — and finding answers means either manually digging through files or paying for a hosted AI service that ingests your sensitive data.

Hosted document AI tools are expensive, opaque, and require you to hand over your files to a third party. On the other hand, building your own RAG pipeline from scratch means weeks of engineering work just to get a working prototype.

**Aktilot fills that gap.** It's a self-hosted, open-source platform that lets you upload your documents and ask questions in plain English — in minutes, not weeks, with your data staying exactly where it is.

---

## What Aktilot Does

- **Organize documents into projects** — separate knowledge bases for different teams, clients, or use cases
- **Create AI agents per project** — each agent gets its own persona and instructions so it answers in the right tone and scope
- **Ask questions, get cited answers** — every response shows exactly which document chunks it drew from, so you can verify the source
- **See inside the pipeline** — keyword extraction, vector search, re-ranking, and context assembly are all surfaced in the UI with timings, so nothing is a black box

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
| Backend | http://localhost:8000 |

That's it. Create a project, upload a PDF, create an agent, and start asking questions.

---

## Local Development

If you want to contribute or run the services individually:

**Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set OPENAI_API_KEY and DATABASE_URL

# Start Postgres via Docker (skip if you have one running)
docker run -d --name aktilot-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=docai \
  -p 5432:5432 postgres:16-alpine

alembic upgrade head
uvicorn main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg) |
| `CHAT_MODEL` | No | Chat model to use (default: `gpt-4o-mini`) |
| `EMBEDDING_MODEL` | No | Embedding model (default: `text-embedding-3-small`) |
| `UPLOAD_DIR` | No | Where uploaded files are stored (default: `uploads`) |
| `CHROMA_DIR` | No | Where vector data is persisted (default: `chroma_data`) |

Copy `.env.example` to `.env` in the project root (for Docker) or `backend/.env` (for local dev).

---

## Contributing

We welcome contributions of all kinds — bug fixes, new features, documentation improvements, and feedback.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up your dev environment, our branching workflow, code standards, and how to submit a pull request.

If you've found a bug, open an [issue](https://github.com/your-org/aktilot/issues). If you have a feature idea, start a [discussion](https://github.com/your-org/aktilot/discussions) before writing code.

For security vulnerabilities, please do not open a public issue — see [SECURITY.md](SECURITY.md).

---

## License

[MIT](LICENSE) © Vikas Pandey
