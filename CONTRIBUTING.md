# Contributing to Aktilot

Thank you for your interest in contributing! This document covers how to set up your development environment, the branching and PR workflow, and the code standards we follow.

By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Issues](#reporting-issues)

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12+ |
| Node.js | 20+ |
| Docker & Docker Compose | latest stable |
| PostgreSQL | 16 (or use the Docker service) |
| Git | any recent version |

---

## Local Setup

### 1. Fork and clone

```bash
git clone https://github.com/<your-fork>/aktilot.git
cd aktilot
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install ruff          # linter

cp .env.example .env
# Edit .env — set OPENAI_API_KEY and DATABASE_URL

# Start Postgres (skip if you have one running locally)
docker run -d --name aktilot-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=docai \
  -p 5432:5432 postgres:16-alpine

alembic upgrade head
uvicorn main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 4. Full stack via Docker

```bash
cp .env.example .env    # set OPENAI_API_KEY
docker compose up --build
```

---

## Development Workflow

- **Branch from `main`** — `git checkout -b feat/my-feature` or `fix/bug-description`
- **One logical change per PR** — keep diffs reviewable
- **Run checks before pushing** (see [Code Standards](#code-standards))
- **Write a clear PR description** — what changed and why; link any related issues

---

## Code Standards

### Backend (Python)

We use **ruff** for linting and formatting.

```bash
cd backend
ruff check .          # lint
ruff format .         # format
ruff check --fix .    # auto-fix safe issues
```

Rules enforced: ruff defaults (`E4`, `E7`, `E9`, `F`) plus `I` (isort). Config lives in `backend/pyproject.toml`.

- Prefer `async def` for all I/O-bound functions
- Use Pydantic models for all request/response schemas — no raw dicts crossing the API boundary
- Keep services free of FastAPI imports; routers are thin wrappers

### Frontend (TypeScript)

```bash
cd frontend
npm run build         # TypeScript compile + Vite build (catches type errors)
```

- All new components go in `src/components/` or `src/pages/`
- State that involves the API belongs in `src/hooks/useApi.ts`
- Use `cn()` from `@/lib/utils` for conditional class names
- No inline styles — Tailwind only

### Database migrations

Any change to a DB model needs an Alembic migration:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
# Review the generated file in alembic/versions/, then:
alembic upgrade head
```

---

## Submitting a Pull Request

1. Push your branch to your fork
2. Open a PR against `main` in the upstream repo
3. Fill in the PR template — summary, test plan, screenshots for UI changes
4. Address review comments
5. Squash-merge once approved

---

## Reporting Issues

- **Bugs** — use the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) template
- **Feature requests** — use the [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) template
- **Security vulnerabilities** — see [SECURITY.md](SECURITY.md) (do not open a public issue)

---

## Questions?

Open a [Discussion](https://github.com/vikas0686/aktilot/discussions) or comment on an existing issue.
