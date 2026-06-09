# Doc AI Assistant

RAG-based document knowledge assistant. Upload PDFs and TXTs, chunk and embed them, then chat with your documents — with full visibility into every processing step.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, FAISS (in-memory), OpenAI API, pypdf
- **Frontend**: React 18, TypeScript, Vite, TailwindCSS, shadcn/ui, TanStack Query v5

## Features

- Drag-and-drop multi-file upload (PDF, TXT)
- On-demand document chunking (1000 chars / 200 overlap)
- OpenAI embeddings stored in FAISS vector store
- Hybrid RAG: keyword match + cosine similarity scoring
- Chat UI with tool execution viewer and retrieved chunk panel
- Vector store stats (total chunks, files chunked, index size)
- Dark mode

## Quick Start (Local Dev)

### Prerequisites

- Python 3.12+
- Node 20+
- An OpenAI API key

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Docker (Production)

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...

docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/files/upload` | Upload a PDF or TXT file |
| `GET` | `/api/files` | List all uploaded files |
| `DELETE` | `/api/files/{id}` | Delete a file and its chunks |
| `POST` | `/api/chunk/{id}` | Chunk a file and embed it |
| `GET` | `/api/chunks/stats` | Vector store statistics |
| `POST` | `/api/chat` | Send a question, get RAG answer |
| `GET` | `/api/tools/history` | Tool execution history |

## Architecture

```
backend/
├── api/routes/        # FastAPI routers (files, chunks, chat)
├── services/          # Business logic (file, chunk, rag)
├── vectorstore/       # FAISS singleton
├── models/            # Pydantic schemas
└── context/           # Uploaded files stored here

frontend/src/
├── pages/             # UploadPage, FilesPage, ChunkPage, ChatPage
├── components/        # Layout, UI primitives
├── hooks/             # React Query hooks
├── services/          # Axios API client
└── types/             # TypeScript interfaces
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required. Your OpenAI API key |
| `CONTEXT_DIR` | `context` | Directory where uploaded files are stored |
