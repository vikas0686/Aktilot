Phase 1 — Backend Infrastructure

Task 1.1 — PostgreSQL connection + Alembic setup
- Add asyncpg, sqlalchemy[asyncio], alembic to requirements
- Create db/session.py with async engine + session factory
- Init Alembic (alembic init), configure env.py to use the async engine
- Test: alembic upgrade head runs without error on empty DB

Task 1.2 — Project table + migration
- Define Project SQLAlchemy model (id, name, description, created_at)
- Generate migration 001_create_projects
- Test: table exists in DB after alembic upgrade head

Task 1.3 — File table + migration
- Define File model (id, project_id FK, filename, filepath, size, chunk_status, chunk_count, uploaded_at)
- Generate migration 002_create_files
- Test: table exists, FK to projects enforced

Task 1.4 — Agent table + migration
- Define Agent model (id, project_id FK, name, description, system_prompt, created_at)
- Generate migration 003_create_agents
- Test: table exists, FK to projects enforced

Task 1.5 — Message table + migration
- Define Message model (id, agent_id FK, r
- Generate migration 004_create_messages
- Test: table exists, FK to agents enforced

Task 1.6 — ChromaDB persistent client setu
- Add chromadb to requirements
- Create vectorstore/chroma_store.py with a persistent client pointed at a configurable path
- Helper: get_collection(project_id) — returns or creates a named collection per project
- Helper: add_chunks(project_id, chunks, e, query_vec, k), delete_file(project_id,file_id)
- Test: create a collection, add a doc, sesurvives process restart

Task 1.7 — Filesystem storage setup
- Add UPLOAD_DIR to config (e.g. ./uploads/{project_id}/)
- Helper to resolve file path given projec
- Test: directory auto-created per project

---
Phase 2 — Projects API

Task 2.1 — Create project endpoint
- POST /api/projects — body: {name, description}
- Inserts into DB, returns ProjectRecord
- Test: 201 with project id returned

Task 2.2 — List projects endpoint
- GET /api/projects — returns list of all
- Test: empty list on fresh DB, populated after creates

Task 2.3 — Get project endpoint
- GET /api/projects/{project_id} — returns
- Test: 404 on unknown id, 200 with correc

Task 2.4 — Delete project endpoint
- DELETE /api/projects/{project_id} — deletes project, cascades to files + agents + messages in DB
- Also deletes filesystem files and Chromat
- Test: 204 on success, subsequent GET returns 404

---
Phase 3 — File Upload + Auto-Chunking

Task 3.1 — Upload file endpoint
- POST /api/projects/{project_id}/files/upload — multipart
- Save file to uploads/{project_id}/filena
- Insert File record in DB with chunk_stat
- Trigger chunking as a FastAPI Background
- Return FileRecord immediately
- Test: file appears on disk, DB record created, status starts as "pending"

Task 3.2 — Chunk service (ChromaDB-backed)
- Read file text (PDF / DOCX / TXT)
- Split into chunks (1000 chars, 200 overl
- Embed via OpenAI in batches
- Store in ChromaDB collection for that project, with metadata: {file_id, filename, chunk_index}
- Update DB File record: chunk_status = "chunked", chunk_count = N
- Test: after chunking, ChromaDB collectioed

Task 3.3 — List files endpoint
- GET /api/projects/{project_id}/files — returns all files for project with chunk status
- Test: empty on new project, reflects sta

Task 3.4 — Delete file endpoint
- DELETE /api/projects/{project_id}/files/{file_id}
- Remove from filesystem, delete chunks fr
- Test: file gone from disk, chunks removed from ChromaDB, 404 on subsequent GET

---
Phase 4 — Agents API

Task 4.1 — Create agent endpoint
- POST /api/projects/{project_id}/agents — body: {name, description, system_prompt}
- Insert into DB, return AgentRecord
- Test: 201 with agent id, FK to project validated

Task 4.2 — List agents endpoint
- GET /api/projects/{project_id}/agents
- Test: returns only agents belonging to t

Task 4.3 — Get agent endpoint
- GET /api/agents/{agent_id} — returns age
- Test: 404 on unknown id

Task 4.4 — Update agent endpoint
- PUT /api/agents/{agent_id} — partial updystem_prompt
- Test: changes persist in DB

Task 4.5 — Delete agent endpoint
- DELETE /api/agents/{agent_id} — deletes
- Test: 204, messages gone

---
Phase 5 — Chat / RAG Pipeline

Task 5.1 — Chat endpoint (RAG with agent s
- POST /api/agents/{agent_id}/chat — body: {question}
- Load agent from DB to get system_prompt
- Run RAG pipeline (below), inject agent s
- Persist user message + assistant message
- Return answer + tool steps + retrieved chunks
- Test: answer returned, 2 messages saved in DB

Task 5.2 — RAG pipeline (per-project ChromaDB)
- Step 1: LLM keyword extraction from ques
- Step 2: Embed question → ChromaDB search 20)
- Step 3: Hybrid re-rank (vector score + keyword match, 0.5/0.5)
- Step 4: Build context from top 3 chunks
- Step 5: LLM final answer — use agent's system_prompt as the system message
- Test: each step produces expected output in LLM call

Task 5.3 — Chat history endpoint
- GET /api/agents/{agent_id}/messages — re
- Test: messages returned in created_at order

---
Phase 6 — Frontend: Projects

Task 6.1 — Projects list page
- Route: / — shows all projects as cards (te)
- Empty state if none
- Test: renders project cards from API

Task 6.2 — Create project modal
- Button on projects list → modal with nam
- On submit: POST /api/projects, close modal, refresh list
- Test: new project appears without page reload

Task 6.3 — Delete project
- Delete button on project card with confirmation
- Test: project disappears from list after confirm

Task 6.4 — Project detail page shell
- Route: /projects/{id} — shows project name, two tabs: "Files" and "Agents"
- Test: navigating to /projects/{id} loads

---
Phase 7 — Frontend: File Management

Task 7.1 — File upload zone in project det
- Drag-and-drop + click-to-browse in "Files" tab
- On drop/select: POST /api/projects/{id}/files/upload
- Show upload spinner per file
- Test: file appears in list after upload

Task 7.2 — File list with chunk status
- Table of files: name, size, chunk status badge (pending / chunking / chunked / error)
- Poll GET /api/projects/{id}/files every ing"/"chunking" state, stop when all
  settled
- Test: badge updates from "pending" → "ch

Task 7.3 — Delete file from UI
- Delete button per row → confirm → DELETEle_id}
- Test: row removed from table

---
Phase 8 — Frontend: Agent Management

Task 8.1 — Agents list in project detail
- "Agents" tab lists agents (name, descrip
- Empty state with "Create Agent" prompt
- Test: agents load for current project

Task 8.2 — Create/edit agent form
- Modal with: Name, Description, System Prompt (textarea)
- Create: POST /api/projects/{id}/agents
- Edit: PUT /api/agents/{id} (pre-filled form)
- Test: new agent appears in list, edits p

Task 8.3 — Delete agent
- Delete button on agent row with confirmation
- Test: agent removed from list

---
Phase 9 — Frontend: Chat UI

Task 9.1 — Agent chat page
- Route: /agents/{agent_id}/chat
- Shows agent name + description in header
- Chat thread (user right, assistant left), input bar + send button
- Test: page loads with correct agent name

Task 9.2 — Send message + display response
- Send question → POST /api/agents/{agent_id}/chat
- Show "Thinking…" spinner while pending
- Append user + assistant messages to thre
- Test: response appears after send

Task 9.3 — Chat history on load
- On page load fetch GET /api/agents/{agent_id}/messages and pre-populate thread
- Test: previous messages visible when rev

Task 9.4 — RAG side panel in chat
- On each assistant response, show collaps
    - Tool steps (name, duration, input/output summary)
    - Retrieved chunks (filename, score, exp
- Test: side panel renders with correct st

---
Summary Table

┌──────────────────────┬─────────┬──────────────────────────────────────────────────────────────────┐
│        Phase         │  Tasks  │        ble                          │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 1 — Infra            │ 1.1–1.7 │ DB migr filesystem setup            │
├──────────────────────┼─────────┼─────────────────────────────────────┤
│ 2 — Projects API     │ 2.1–2.4 │ CRUD en                             │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 3 — Files + Chunking │ 3.1–3.4 │ Upload,, delete                     │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 4 — Agents API       │ 4.1–4.5 │ CRUD en                             │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 5 — Chat / RAG       │ 5.1–5.3 │ RAG pipjection, message persistence │
├──────────────────────┼─────────┼─────────────────────────────────────┤
│ 6 — UI: Projects     │ 6.1–6.4 │ List, c                             │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 7 — UI: Files        │ 7.1–7.3 │ Upload,                             │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 8 — UI: Agents       │ 8.1–8.3 │ List, c                             │
├──────────────────────┼─────────┼──────────────────────────────────────────────────────────────────┤
│ 9 — UI: Chat         │ 9.1–9.4 │ Chat UIpanel                        │
└──────────────────────┴─────────┴─────────────────────────────────────┘

Total: 30 tasks — each independently deployable and verifiable.

Phases 1–5 (backend) can be built and teste frontend. Phases 6–9 depend only on theAPI contracts being stable, so frontend wos are done.