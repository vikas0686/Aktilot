# GitHub Connector

The Knowledge Base landing page links to a dedicated **GitHub Repository** route alongside **Uploaded Files**. It lets a project ingest an entire GitHub repository — file contents and issues (with comments) — into the same searchable vector store as uploaded documents, kept as a clearly separate, independently-syncable source.

---

## How it works

```text
GitHub App (installed on your org/account)
    │
    │  install → signed state param → callback
    ▼
Aktilot backend
    │
    │  GithubSyncWorkflow (Temporal, durable, checkpointed per step)
    │    fetch repo tree → fetch file contents → fetch issues+comments
    │    → clear old chunks for this repo → embed & index
    ▼
ChromaDB (same per-project collection as uploads, tagged source_type=github)
```

- Ingestion scope: all text/code files under the configured branch (binaries, lockfiles, and common build/dependency directories are skipped; files over 500 KB are skipped), plus all issues and their comments. Pull requests are not ingested.
- Sync is **manual only** — there are no webhooks in this version. Clicking **Sync** on a connected repo deletes that repo's existing chunks and re-pulls everything fresh; nothing is diffed incrementally.
- Raw repo/issue content is never exposed in the UI — only per-repo aggregate stats (chunk count, sync status, last synced time). It reads the same way `FilesTab` shows upload status without a file browser.
- Retrieval is source-agnostic: an agent's chat queries search both uploaded-file chunks and GitHub chunks in the same collection.

---

## Why you need your own GitHub App

GitHub Apps have exactly **one** Setup URL configured at the App level — it can't be templated per-deployment. Aktilot is self-hosted software with no central multi-tenant control plane, so **each deployment (your laptop, your team's staging server, your production instance) needs its own GitHub App**, pointing at that deployment's own domain.

This is the standard pattern for self-hosted tools that integrate with GitHub Apps (same model used by self-hosted CI runners, self-hosted Git importers, etc.) — it's a one-time setup step per deployment, not something every user of that deployment repeats. If Aktilot is ever offered as a centrally-hosted product with real multi-tenancy, a single vendor-owned App on a fixed domain would replace this — but that's not the architecture today.

---

## Setup

### 1. Create the GitHub App

Go to **GitHub → Settings → Developer settings → GitHub Apps → New GitHub App** (use your org's settings if installing org-wide).

| Field | Value |
|---|---|
| GitHub App name | Anything unique, e.g. `Aktilot Knowledge Connector` |
| Homepage URL | Your Aktilot frontend URL (e.g. `http://localhost:3000`) — required but not otherwise used |
| **Setup URL** | `<your-backend-url>/api/github/install/callback`, e.g. `http://localhost:8000/api/github/install/callback` |
| Webhook → Active | **Unchecked** — this version doesn't use webhooks |
| Repository permissions | `Contents` = Read-only, `Issues` = Read-only (`Metadata` auto-selects) |
| Where can this be installed | "Only on this account" is simplest for a single deployment |

> **Setup URL ≠ Callback URL.** GitHub Apps have two similarly-named fields. **Callback URL** is only used for user-to-server OAuth (not used here). **Setup URL** is the one that controls the post-install redirect — it's what must be set to `.../api/github/install/callback`. If you set the wrong one, installing the App leaves you stranded on GitHub's own `github.com/settings/installations/<id>` page instead of bouncing back to Aktilot — see [Troubleshooting](#troubleshooting) if that happens.

Click **Create GitHub App**.

### 2. Collect the credentials

- **App ID** — numeric, shown near the top of the App's settings page.
- **App slug** — from the URL bar: `github.com/settings/apps/<slug>`.
- **Private key** — click **Generate a private key**; downloads a `.pem` file.

### 3. Format the private key for `.env`

`.env` files don't support real multi-line values reliably, so the PEM's newlines need to be escaped to literal `\n`:

```bash
awk '{printf "%s\\n", $0}' ~/Downloads/your-app.*.private-key.pem
```

Copy the single-line output as-is — no surrounding quotes needed.

### 4. Set environment variables

In the repo root `.env` (Docker Compose) or `backend/.env` (local dev):

```bash
GITHUB_APP_ID=123456
GITHUB_APP_SLUG=aktilot-knowledge-connector
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n
GITHUB_APP_STATE_SECRET=<random secret, e.g. `openssl rand -hex 32`>
FRONTEND_BASE_URL=http://localhost:3000
```

| Variable | Required | Description |
|---|---|---|
| `GITHUB_APP_ID` | Yes | Numeric App ID from the App's settings page |
| `GITHUB_APP_SLUG` | Yes | App slug, used to build the install URL (`github.com/apps/<slug>/installations/new`) |
| `GITHUB_APP_PRIVATE_KEY` | Yes | The downloaded PEM, with real newlines replaced by literal `\n` |
| `GITHUB_APP_STATE_SECRET` | Yes | Random secret used to HMAC-sign the `state` param carrying project identity through the install redirect |
| `FRONTEND_BASE_URL` | Yes | Where the backend redirects the browser back to after install completes (default: `http://localhost:3000`) |

### 5. Restart the backend and worker

```bash
docker compose up -d --build backend worker
```

(Local dev without Docker: restart `uvicorn main:app` and `python -m temporal.worker` after sourcing the updated `.env`.)

---

## Using it

1. Open a project's **Knowledge Base** page → **GitHub Repository** card → `/github` route.
2. Click **Connect GitHub** — you're redirected to GitHub's install page for your App.
3. Choose the account/org and grant access to one or more repositories, then confirm. GitHub redirects back to the project with the installation recorded.
4. Click **Add Repository** and pick a repo the installation can see. This kicks off the first sync.
5. Once `sync_status` shows **Synced**, the repo's chunks are searchable by any agent in that project.
6. To pull in new commits/issues later, click the refresh icon on that repo's row — this deletes its old chunks and re-ingests everything from scratch.
7. **Disconnect** on a repo row removes just that repo's chunks and connection. **Disconnect** at the installation level revokes the App's access entirely and removes all connected repos for that project.

---

## Troubleshooting

**"Connect GitHub" returns a 503** — `GITHUB_APP_SLUG` or `GITHUB_APP_STATE_SECRET` isn't set. Confirm both are present in the environment the backend container/process actually reads (check with `docker compose config` if using Compose).

**Install finishes but you land on `github.com/settings/installations/<id>` instead of back in Aktilot** — the App's **Setup URL** field is empty or was accidentally set to the Callback URL field instead (see the callout in step 1). Fix it under the App's settings, then either:
- Reinstall the App (uninstall from `github.com/settings/installations/<id>` → **Configure** → **Uninstall**, then reinstall) so GitHub redirects through the now-correct Setup URL, or
- If you have backend access, the installation already exists on GitHub's side and can be linked without reinstalling: call `GET /api/projects/{project_id}/github/install-url` to get a freshly-signed `state`, then hit `GET /api/github/install/callback?installation_id=<id>&setup_action=install&state=<that state>` directly — this replays what the browser redirect would have done.

**Redirected back with `?github=error`** — the `state` param failed verification (expired after 10 minutes, or `GITHUB_APP_STATE_SECRET` changed between generating the install URL and completing the flow). Click **Connect GitHub** again.

**A repo won't appear in "Add Repository"** — the installation wasn't granted access to it. Go to GitHub → Settings → Applications → your App → **Configure**, and add the repository to the installation's repository access list.

**Sync stuck in "Syncing…"** — check the Temporal UI (`:8233` in Docker Compose) for the `gh-sync-<connection_id>` workflow to see which activity is retrying and why (commonly a GitHub rate limit or an auth/permission error on that repo).
