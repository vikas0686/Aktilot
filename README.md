# Doc AI Assistant

A RAG-based document assistant. Upload your files, chunk and embed them, then chat with your documents — with full visibility into every processing step.

---

## Problem Statement

Knowledge trapped in documents is hard to query. Teams maintain large collections of PDFs, Word files, and text documents — policies, specs, runbooks, contracts — but finding a specific answer means manually searching through dozens of files. Generic AI chatbots hallucinate because they have no access to your private documents. Existing enterprise search tools are expensive, require complex infrastructure, and offer no transparency into how answers are derived.

---

## Solution

Doc AI Assistant lets you upload your own documents, embed them into a local vector store, and chat with them using a custom RAG (Retrieval-Augmented Generation) pipeline. Every step of the pipeline — keyword extraction, chunk retrieval, ranking, context assembly, LLM call — is surfaced in the UI so you can see exactly how each answer was produced.

**Key properties:**
- Fully private — documents never leave your infrastructure
- No external search service — FAISS runs in-memory
- Transparent — every tool step shown with timing, input, and output
- Supports PDF, TXT, DOC, DOCX
- Single-command Docker deployment

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Browser                          │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │Documents │  │Context Files │  │  Chat Assistant   │ │
│  │(Upload + │  │  (List +     │  │  ┌─────────────┐  │ │
│  │ Chunk)   │  │   Delete)    │  │  │ Tool Steps  │  │ │
│  └────┬─────┘  └──────┬───────┘  │  │ Ret. Chunks │  │ │
│       │               │          │  └─────────────┘  │ │
└───────┼───────────────┼──────────┴────────┬───────────┘
        │ React + TS + Vite + TanStack Query │
        │           Axios / API proxy        │
        ▼                                    ▼
┌───────────────────────────────────────────────────────┐
│                    FastAPI Backend                    │
│                                                       │
│  POST /api/files/upload   GET /api/files              │
│  DELETE /api/files/{id}   POST /api/chunk/{id}        │
│  GET /api/chunks/stats    POST /api/chat              │
│  GET /api/tools/history                               │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ FileService │  │ ChunkService │  │  RAGService │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘  │
│         │                │                  │         │
│         ▼                ▼                  ▼         │
│  ┌────────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │ /context   │  │  FAISS Store  │  │ OpenAI API  │  │
│  │ (disk)     │  │  (in-memory)  │  │ gpt-4o-mini │  │
│  └────────────┘  └───────────────┘  └─────────────┘  │
└───────────────────────────────────────────────────────┘
```

---

## RAG Pipeline Flow

When a user sends a question, the backend executes five sequential steps:

```
User Question
      │
      ▼
┌─────────────────┐
│ 1. Extract      │  gpt-4o-mini extracts search keywords
│    Keywords     │  → ["settlement", "retry", "rules"]
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Search       │  Embed question → cosine similarity on FAISS
│    Chunks       │  + keyword match ratio per chunk
└────────┬────────┘    score = 0.5 × vector_sim + 0.5 × keyword_ratio
         │
         ▼
┌─────────────────┐
│ 3. Rank Chunks  │  Sort all candidates by hybrid score descending
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Build        │  Take top 3 chunks, assemble context string
│    Context      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Generate     │  gpt-4o-mini with system prompt + context + question
│    Response     │
└────────┬────────┘
         │
         ▼
   Answer + Tool Steps + Retrieved Chunks → UI
```

---

## User Journey

```
1. Open app → lands on Documents screen

2. Drag & drop one or more files (PDF / TXT / DOC / DOCX)
   └── File saved to /context on disk
   └── File appears in the table with "Not chunked" badge

3. Click "Chunk" on a file
   └── File is read and split into 1000-char chunks (200 overlap)
   └── Each chunk is embedded via OpenAI text-embedding-3-small
   └── Embeddings stored in FAISS in-memory index
   └── Badge updates to "N chunks"
   └── Stats bar updates: Total Chunks / Files Chunked / Index Size

4. Navigate to Context Files
   └── View all uploaded files with size, upload time, chunk status
   └── Delete any file (removes from disk + vector store)

5. Navigate to Chat Assistant
   └── Type a question, press Enter
   └── Typing indicator appears while processing
   └── Answer appears in the chat thread
   └── Right panel updates with:
       • Tools Executed — each step with name, duration, input/output (expandable)
       • Retrieved Chunks — top 3 chunks with hybrid score (expandable)

6. Ask follow-up questions
   └── Tool panel and chunk panel refresh for every new message
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node 20+
- OpenAI API key

### Local Development

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set OPENAI_API_KEY=sk-...
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### Docker

```bash
cp .env.example .env          # set OPENAI_API_KEY=sk-...
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/files/upload` | Upload a file (PDF, TXT, DOC, DOCX) |
| `GET` | `/api/files` | List all uploaded files |
| `DELETE` | `/api/files/{id}` | Delete a file and its vector chunks |
| `POST` | `/api/chunk/{id}` | Chunk and embed a file into FAISS |
| `GET` | `/api/chunks/stats` | Vector store statistics |
| `POST` | `/api/chat` | Send a question, receive RAG answer |
| `GET` | `/api/tools/history` | Tool execution history (in-memory) |

---

## Project Structure

```
doc-ai-assistant/
├── backend/
│   ├── api/routes/          # files.py · chunks.py · chat.py
│   ├── services/            # file_service · chunk_service · rag_service
│   ├── vectorstore/         # faiss_store.py (singleton)
│   ├── models/              # Pydantic schemas
│   ├── context/             # uploaded files stored here
│   ├── config.py            # pydantic-settings env config
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/           # UploadPage · FilesPage · ChatPage
│   │   ├── components/      # Layout · ui primitives
│   │   ├── hooks/           # useApi · useDarkMode
│   │   ├── services/        # axios client
│   │   └── types/           # TypeScript interfaces
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required. Your OpenAI API key |
| `CONTEXT_DIR` | `context` | Directory where uploaded files are stored |

---

## Next Enhancements

| Priority | Enhancement | Notes |
|----------|-------------|-------|
| High | **Persistent vector store** | Serialize FAISS index to disk on write so embeddings survive server restarts |
| High | **SQLite metadata store** | Replace in-memory dicts with SQLite so file records persist across restarts |
| High | **Streaming responses** | Stream LLM tokens to the chat UI via SSE for faster perceived response time |
| Medium | **Multi-user / auth** | Add JWT-based auth so multiple users can have isolated document collections |
| Medium | **Re-ranking** | Add a cross-encoder reranker (e.g. `cross-encoder/ms-marco-MiniLM`) after FAISS retrieval for higher precision |
| Medium | **Chunk size configurability** | Let users set chunk size and overlap per file from the UI |
| Medium | **Table / image extraction** | Use `pdfplumber` or `unstructured` to extract tables and images from PDFs |
| Low | **Conversation memory** | Pass prior turns as context so the LLM can handle follow-up questions correctly |
| Low | **Export chat** | Download conversation + retrieved chunks as PDF or Markdown |
| Low | **File preview** | Inline document viewer (PDF.js for PDFs) alongside the chat |
| Low | **Observability** | Add OpenTelemetry tracing for RAG steps and log to a collector |
