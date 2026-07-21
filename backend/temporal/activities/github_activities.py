"""
Activities for GithubSyncWorkflow — each step is independently retryable and
mirrors document_activities.py's temp-file-on-disk convention: large repo
payloads (file trees, blob contents, issue threads) are written to disk
between activities instead of flowing through Temporal workflow history,
which caps individual payloads at 4 MB.

Pipeline:
  mark_connection_syncing        — Postgres write
  fetch_repo_tree                — Git Trees API, filtered to indexable blobs
  fetch_file_contents            — Git Blobs API + chunking, reads the tree file
  fetch_issues                   — Issues + comments API, chunked per issue
  clear_existing_vectors_for_repo — ChromaDB delete for this repo_id (idempotent)
  embed_and_index_github_chunks  — embeds file+issue chunks, indexes to ChromaDB
  mark_connection_synced / mark_connection_error — final Postgres status write
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

import db.models  # noqa: F401 — side-effect import: registers all SQLAlchemy mappers
from config import settings
from db.models.github_connection import GithubConnection
from db.session import AsyncSessionFactory
from services.github import client as gh_client
from services.github.app_auth import get_installation_token
from services.llm import get_embedding_provider
from services.llm.base import ProviderAuthError, ProviderNotAvailableError
from services.project_chunk_service import _split_text
from vectorstore.chroma_store import add_chunks
from vectorstore.chroma_store import delete_by_repo as chroma_delete_by_repo

_EMBED_BATCH = 100  # matches project_chunk_service.EMBED_BATCH
_MAX_BLOB_SIZE = 500_000  # skip files larger than this (bytes)
_BLOB_FETCH_CONCURRENCY = 10

_IGNORED_PATH_PREFIXES = (
    ".git/",
    "node_modules/",
    "dist/",
    "build/",
    "vendor/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".next/",
    "target/",
)
_IGNORED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".bmp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".mp4",
    ".mp3",
    ".mov",
    ".avi",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".bin",
    ".pyc",
}
_IGNORED_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "Gemfile.lock",
    "composer.lock",
}


def _should_index_path(path: str, size: int) -> bool:
    if size > _MAX_BLOB_SIZE:
        return False
    if any(path.startswith(p) or f"/{p}" in path for p in _IGNORED_PATH_PREFIXES):
        return False
    name = path.rsplit("/", 1)[-1]
    if name in _IGNORED_FILENAMES:
        return False
    if Path(name).suffix.lower() in _IGNORED_EXTENSIONS:
        return False
    return True


def _tree_path(project_id: str, connection_id: str) -> Path:
    return settings.upload_dir / project_id / f"gh_{connection_id}_tree.json"


def _file_chunks_path(project_id: str, connection_id: str) -> Path:
    return settings.upload_dir / project_id / f"gh_{connection_id}_file_chunks.json"


def _issue_chunks_path(project_id: str, connection_id: str) -> Path:
    return settings.upload_dir / project_id / f"gh_{connection_id}_issue_chunks.json"


@activity.defn
async def mark_connection_syncing(connection_id: str) -> None:
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(GithubConnection).where(
                GithubConnection.id == uuid.UUID(connection_id)
            )
        )
        record = result.scalar_one()
        record.sync_status = "syncing"
        record.error_message = None
        await db.commit()


@activity.defn
async def mark_connection_synced(
    connection_id: str,
    file_count: int,
    issue_count: int,
    chunk_count: int,
    tree_truncated: bool,
) -> None:
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(GithubConnection).where(
                GithubConnection.id == uuid.UUID(connection_id)
            )
        )
        record = result.scalar_one()
        record.sync_status = "synced"
        record.file_count = file_count
        record.issue_count = issue_count
        record.chunk_count = chunk_count
        record.tree_truncated = tree_truncated
        record.last_synced_at = datetime.now(timezone.utc)
        record.error_message = None
        await db.commit()


@activity.defn
async def mark_connection_error(connection_id: str, message: str) -> None:
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(GithubConnection).where(
                GithubConnection.id == uuid.UUID(connection_id)
            )
        )
        record = result.scalar_one()
        record.sync_status = "error"
        record.error_message = message[:2000]
        await db.commit()


@activity.defn
async def fetch_repo_tree(
    connection_id: str,
    project_id: str,
    installation_id: int,
    repo_full_name: str,
    branch: str,
) -> dict:
    """Lists the repo's recursive file tree, filters to indexable blobs, writes
    {path, sha, size} entries to a temp JSON file. Returns
    {"count": filtered count, "truncated": whether GitHub's tree API truncated
    the result}."""
    token = await get_installation_token(installation_id)
    try:
        tree, truncated = await gh_client.get_tree(token, repo_full_name, branch)
    except (gh_client.GithubAuthError, gh_client.GithubNotFoundError) as exc:
        raise ApplicationError(str(exc), non_retryable=True) from exc

    filtered = [
        {"path": item["path"], "sha": item["sha"], "size": item.get("size", 0)}
        for item in tree
        if _should_index_path(item["path"], item.get("size", 0))
    ]

    out = _tree_path(project_id, connection_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(filtered))
    return {"count": len(filtered), "truncated": truncated}


@activity.defn
async def fetch_file_contents(
    connection_id: str,
    project_id: str,
    installation_id: int,
    repo_full_name: str,
) -> int:
    """Reads the filtered tree, fetches each blob's content (bounded concurrency),
    splits into chunks, writes {path, chunk_index, content} entries to a temp file."""
    tree_file = _tree_path(project_id, connection_id)
    if not tree_file.exists():
        raise ApplicationError(
            f"Repo tree file missing: {tree_file}", non_retryable=True
        )
    items: list[dict] = json.loads(tree_file.read_text())

    token = await get_installation_token(installation_id)
    sem = asyncio.Semaphore(_BLOB_FETCH_CONCURRENCY)
    chunks: list[dict] = []

    async def _fetch_and_split(item: dict) -> None:
        async with sem:
            try:
                content = await gh_client.get_blob(token, repo_full_name, item["sha"])
            except gh_client.GithubNotFoundError:
                return
            for i, text in enumerate(_split_text(content)):
                chunks.append({"path": item["path"], "chunk_index": i, "content": text})

    batch_size = 50
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        await asyncio.gather(*[_fetch_and_split(it) for it in batch])
        activity.heartbeat(start + len(batch))

    out = _file_chunks_path(project_id, connection_id)
    out.write_text(json.dumps(chunks))
    tree_file.unlink(missing_ok=True)
    return len(items)


@activity.defn
async def fetch_issues(
    connection_id: str,
    project_id: str,
    installation_id: int,
    repo_full_name: str,
) -> int:
    """Fetches all issues (with comments), builds one document per issue,
    chunks it, writes {path, chunk_index, content} entries to a temp file."""
    token = await get_installation_token(installation_id)
    try:
        issues = await gh_client.list_issues(token, repo_full_name)
    except (gh_client.GithubAuthError, gh_client.GithubNotFoundError) as exc:
        raise ApplicationError(str(exc), non_retryable=True) from exc

    chunks: list[dict] = []
    for idx, issue in enumerate(issues):
        comments_text = ""
        if issue.get("comments", 0) > 0:
            try:
                comments = await gh_client.list_issue_comments(
                    token, repo_full_name, issue["number"]
                )
                comments_text = "\n\n".join(
                    f"{(c.get('user') or {}).get('login', 'unknown')}: {c['body']}"
                    for c in comments
                    if c.get("body")
                )
            except gh_client.GithubNotFoundError:
                comments_text = ""

        body = issue.get("body") or ""
        doc = f"Issue #{issue['number']}: {issue['title']}\n\n{body}"
        if comments_text:
            doc += f"\n\n---\nComments:\n{comments_text}"

        for i, text in enumerate(_split_text(doc)):
            chunks.append(
                {"path": f"issues/{issue['number']}", "chunk_index": i, "content": text}
            )

        if idx % 20 == 0:
            activity.heartbeat(idx)

    out = _issue_chunks_path(project_id, connection_id)
    out.write_text(json.dumps(chunks))
    return len(issues)


@activity.defn
async def clear_existing_vectors_for_repo(project_id: str, connection_id: str) -> None:
    chroma_delete_by_repo(project_id, connection_id)


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    provider = get_embedding_provider()
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH):
        batch = texts[i : i + _EMBED_BATCH]
        result = await provider.embed(model=settings.embedding_model, texts=batch)
        embeddings.extend(result.embeddings)
        activity.heartbeat(i)
    return embeddings


@activity.defn
async def embed_and_index_github_chunks(
    connection_id: str, project_id: str, repo_full_name: str
) -> int:
    """Reads the file+issue chunk temp files, embeds everything, indexes to
    ChromaDB tagged source_type=github, then deletes the temp files."""
    file_chunks_file = _file_chunks_path(project_id, connection_id)
    issue_chunks_file = _issue_chunks_path(project_id, connection_id)

    file_chunks = (
        json.loads(file_chunks_file.read_text()) if file_chunks_file.exists() else []
    )
    issue_chunks = (
        json.loads(issue_chunks_file.read_text()) if issue_chunks_file.exists() else []
    )

    all_chunks = [{**c, "ref_type": "file"} for c in file_chunks] + [
        {**c, "ref_type": "issue"} for c in issue_chunks
    ]

    if not all_chunks:
        file_chunks_file.unlink(missing_ok=True)
        issue_chunks_file.unlink(missing_ok=True)
        return 0

    texts = [c["content"] for c in all_chunks]
    try:
        embeddings = await _embed_texts(texts)
    except ProviderAuthError as exc:
        raise ApplicationError(str(exc), non_retryable=True) from exc
    except ProviderNotAvailableError as exc:
        raise ApplicationError(str(exc), non_retryable=True) from exc

    chunk_dicts = [
        {
            "id": f"{connection_id}:{c['ref_type']}:{c['path']}:{c['chunk_index']}",
            "content": c["content"],
            "metadata": {
                "source_type": "github",
                "repo_id": connection_id,
                "repo_full_name": repo_full_name,
                "ref_type": c["ref_type"],
                "path": c["path"],
                # retrieval/ranking (chat_activities.hybrid_rank) and the
                # RetrievedChunk response schema are source-agnostic and always
                # read "filename" as the display label — upload chunks set it to
                # the uploaded filename, so GitHub chunks need an equivalent here.
                "filename": f"{repo_full_name}:{c['path']}",
                "chunk_index": c["chunk_index"],
            },
        }
        for c in all_chunks
    ]

    add_chunks(project_id, chunk_dicts, embeddings)

    file_chunks_file.unlink(missing_ok=True)
    issue_chunks_file.unlink(missing_ok=True)

    return len(all_chunks)
