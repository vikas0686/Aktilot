# Aktilot — Your AI Copilot for Documents

Aktilot is an open-source, self-hosted RAG platform. Organise documents into **projects**, create **AI agents** per project with custom system prompts, and chat with your documents — with full visibility into every step of the retrieval pipeline.

> All data stays on your infrastructure. No third-party search service required.

---

## Features

- **Multi-project workspace** — keep separate knowledge bases for different teams or use cases
- **Per-project agents** — multiple agents per project, each with its own system prompt and configurable chunk budget (`top_k`)
- **Hybrid BM25 + vector retrieval** — cosine similarity (ChromaDB) re-ranked with BM25 for higher precision
- **Full pipeline transparency** — every step (keyword extraction → vector search → BM25 rank → context assembly → LLM call) surfaced in the chat UI with timings
- **Source attribution** — each answer shows which document chunks were used, with Vec / BM25 / hybrid score breakdown
- **Markdown responses** — answers rendered with full GFM (tables, code blocks, lists)
- **One-command Docker deployment** — PostgreSQL + ChromaDB + backend + frontend, all wired up
- **Dark mode**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, TanStack Query, React Router v6 |
| Backend | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2 |
| Vector store | ChromaDB (persistent, per-project collections) |
| Ranking | OpenAI `text-embedding-3-small` + BM25 (`rank-bm25`) |
| LLM | OpenAI `gpt-4o-mini` (configurable) |
| Database | PostgreSQL 16 |
| Container | Docker Compose |

---

## Architecture

```
Browser
  │  React + TypeScript + TanStack Query
  │  Axios → /api/*
  ▼
FastAPI Backend
  ├── /api/projects          Projects CRUD
  ├── /api/projects/:id/files   Upload, chunk, delete files
  ├── /api/projects/:id/agents  Agent management
  └── /api/agents/:id/chat      RAG chat + message history
  │
  ├── PostgreSQL             projects · files · agents · messages
  ├── ChromaDB               one collection per project (cosine distance)
  └── OpenAI API             embeddings (text-embedding-3-small) + chat (gpt-4o-mini)
```

### RAG Pipeline (per chat request)

```
Question
  │
  ▼  Step 1 — Extract Keywords
     LLM extracts search terms  →  ["invoice", "due date"]
  │
  ▼  Step 2 — Vector Search
     Embed question → ChromaDB cosine search  →  top 20 candidates
  │
  ▼  Step 3 — BM25 + Hybrid Rank
     BM25Okapi on candidates, normalise
     final_score = 0.5 × vec_score + 0.5 × bm25_score
     Sort descending
  │
  ▼  Step 4 — Build Context
     Take agent.top_k chunks (default 2), assemble context string
  │
  ▼  Step 5 — Generate Answer
     System prompt + context + question  →  gpt-4o-mini
  │
  ▼
Answer + keywords + source chunks (with score breakdown) + pipeline steps
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose, **or** Python 3.12+ and Node 20+
- An OpenAI API key

### Docker (recommended)

```bash
git clone https://github.com/your-org/aktilot.git
cd aktilot

cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...

docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Local Development

**Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # set OPENAI_API_KEY and DATABASE_URL

# start postgres (or use Docker just for the DB)
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
npm run dev                   # http://localhost:5173
```

---

## Environment Variables

Copy `.env.example` to `.env` in the project root before running Docker Compose, or copy `backend/.env.example` to `backend/.env` for local development.

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | Your OpenAI API key |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string (asyncpg driver) |
| `UPLOAD_DIR` | No | `uploads` | Directory for uploaded files |
| `CHROMA_DIR` | No | `chroma_data` | Directory for ChromaDB persistence |
| `CONTEXT_DIR` | No | `context` | Legacy context directory |
| `CHAT_MODEL` | No | `gpt-4o-mini` | OpenAI chat model |
| `EMBEDDING_MODEL` | No | `text-embedding-3-small` | OpenAI embedding model |

---

## Project Structure

```
aktilot/
├── backend/
│   ├── api/routes/           # projects · files · agents · agent_chat · chat
│   ├── db/
│   │   ├── models/           # Project · File · Agent · Message (SQLAlchemy)
│   │   └── session.py        # async engine + session factory
│   ├── alembic/              # database migrations
│   ├── services/             # project · file · agent · RAG · chunk services
│   ├── vectorstore/          # chroma_store.py — add/search/delete chunks
│   ├── models/schemas.py     # Pydantic request/response models
│   ├── config.py             # pydantic-settings env config
│   ├── main.py               # FastAPI app + router registration
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/            # ProjectsPage · ProjectDetailPage · ProjectAgentsPage · AgentChatPage
│   │   ├── components/       # AppShell · Sidebar · AgentsTab · FilesTab · AktilotIcon · ui/
│   │   ├── hooks/            # useApi · useDarkMode
│   │   ├── services/         # axios API client
│   │   └── types/            # TypeScript interfaces
│   ├── public/               # aktilot-icon.svg
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## API Reference

### Projects

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create a project |
| `GET` | `/api/projects/:id` | Get a project |
| `DELETE` | `/api/projects/:id` | Delete project + all files, agents, messages, and vectors |

### Files

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects/:id/files` | List project files |
| `POST` | `/api/projects/:id/files` | Upload a file (PDF, TXT, DOC, DOCX) |
| `DELETE` | `/api/projects/:id/files/:fid` | Delete file + its vector chunks |

### Agents

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects/:id/agents` | List agents for a project |
| `POST` | `/api/projects/:id/agents` | Create an agent |
| `GET` | `/api/agents/:id` | Get an agent |
| `PUT` | `/api/agents/:id` | Update agent (name, system prompt, top_k) |
| `DELETE` | `/api/agents/:id` | Delete agent + its message history |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents/:id/chat` | Send a question, receive RAG answer |
| `GET` | `/api/agents/:id/messages` | Retrieve chat history for an agent |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

[MIT](LICENSE) © Vikas Pandey
