import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.exceptions import WorkflowAlreadyStartedError

from config import settings
from db.session import get_db
from models.schemas import (
    GithubAvailableRepo,
    GithubConnectionCreate,
    GithubConnectionResponse,
    GithubInstallationResponse,
    GithubInstallUrlResponse,
)
from services import (
    github_connection_service,
    github_installation_service,
    project_service,
)
from services.github import client as gh_client
from services.github.app_auth import get_installation_token
from temporal.client import get_temporal_client
from temporal.workflows.github_sync_workflow import TASK_QUEUE, GithubSyncWorkflow
from vectorstore.chroma_store import delete_by_repo as chroma_delete_by_repo

router = APIRouter(prefix="/api/projects", tags=["github-connector"])
# GitHub's App settings only accept one fixed callback URL — it can't be
# templated per-project, so project identity travels in the signed `state`.
callback_router = APIRouter(tags=["github-connector"])

_STATE_TTL_SECONDS = 600  # 10 minutes to complete the install flow on GitHub's side


def _sign_state(project_id: str) -> str:
    expires_at = int(time.time()) + _STATE_TTL_SECONDS
    payload = f"{project_id}.{expires_at}"
    sig = hmac.new(
        settings.github_app_state_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{sig}"


def _verify_state(state: str) -> uuid.UUID:
    try:
        project_id_str, expires_at_str, sig = state.split(".", 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    expected_sig = hmac.new(
        settings.github_app_state_secret.encode(),
        f"{project_id_str}.{expires_at_str}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        raise HTTPException(status_code=400, detail="Invalid state signature")
    if int(expires_at_str) < time.time():
        raise HTTPException(status_code=400, detail="State parameter expired")

    return uuid.UUID(project_id_str)


@router.get("/{project_id}/github/install-url", response_model=GithubInstallUrlResponse)
async def get_install_url(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await project_service.get(db, project_id)
    if not settings.github_app_slug or not settings.github_app_state_secret:
        raise HTTPException(status_code=503, detail="GitHub App is not configured")

    state = _sign_state(str(project_id))
    install_url = (
        f"https://github.com/apps/{settings.github_app_slug}/installations/new"
        f"?state={state}"
    )
    return GithubInstallUrlResponse(install_url=install_url)


@callback_router.get("/api/github/install/callback")
async def install_callback(
    installation_id: int,
    state: str,
    setup_action: str = "",
    db: AsyncSession = Depends(get_db),
):
    project_id = _verify_state(state)
    await project_service.get(db, project_id)

    if setup_action in ("", "install"):
        try:
            details = await gh_client.get_installation(installation_id)
            account = details.get("account") or {}
            account_login = account.get("login", "unknown")
            account_type = account.get("type", "unknown")
        except Exception:
            account_login, account_type = "unknown", "unknown"

        await github_installation_service.upsert(
            db,
            project_id=project_id,
            installation_id=installation_id,
            account_login=account_login,
            account_type=account_type,
        )
        redirect_url = f"{settings.frontend_base_url}/projects/{project_id}/github?github=connected"
    else:
        redirect_url = (
            f"{settings.frontend_base_url}/projects/{project_id}/github?github=error"
        )

    return RedirectResponse(
        url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@router.get(
    "/{project_id}/github/installation",
    response_model=GithubInstallationResponse,
)
async def get_installation_status(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    return await github_installation_service.require_for_project(db, project_id)


@router.delete(
    "/{project_id}/github/installation",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_installation(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    installation = await github_installation_service.require_for_project(db, project_id)
    connections = await github_connection_service.list_for_project(db, project_id)
    for connection in connections:
        chroma_delete_by_repo(str(project_id), str(connection.id))

    try:
        await gh_client.uninstall_app(installation.installation_id)
    except Exception:
        pass  # best-effort — local records are removed regardless

    await github_installation_service.delete(db, installation)


@router.get(
    "/{project_id}/github/available-repos",
    response_model=list[GithubAvailableRepo],
)
async def list_available_repos(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    installation = await github_installation_service.require_for_project(db, project_id)
    token = await get_installation_token(installation.installation_id)
    repos = await gh_client.list_installation_repos(token)

    connected = {
        c.repo_full_name
        for c in await github_connection_service.list_for_project(db, project_id)
    }
    return [r for r in repos if r["full_name"] not in connected]


@router.post(
    "/{project_id}/github/connections",
    response_model=GithubConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_repo(
    project_id: uuid.UUID,
    body: GithubConnectionCreate,
    db: AsyncSession = Depends(get_db),
):
    installation = await github_installation_service.require_for_project(db, project_id)
    token = await get_installation_token(installation.installation_id)

    branch = body.branch
    if not branch:
        repos = await gh_client.list_installation_repos(token)
        match = next((r for r in repos if r["full_name"] == body.repo_full_name), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail=f"{body.repo_full_name} is not accessible to this installation",
            )
        branch = match["default_branch"]

    record = await github_connection_service.create(
        db, project_id, installation.id, body.repo_full_name, branch
    )

    tc = await get_temporal_client()
    await tc.start_workflow(
        GithubSyncWorkflow.run,
        args=[
            str(record.id),
            str(project_id),
            installation.installation_id,
            body.repo_full_name,
            branch,
            "full",
        ],
        id=f"gh-sync-{record.id}",
        task_queue=TASK_QUEUE,
    )
    return record


@router.get(
    "/{project_id}/github/connections",
    response_model=list[GithubConnectionResponse],
)
async def list_connections(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await project_service.get(db, project_id)
    return await github_connection_service.list_for_project(db, project_id)


@router.post(
    "/{project_id}/github/connections/{connection_id}/sync",
    response_model=GithubConnectionResponse,
)
async def sync_connection(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    connection = await github_connection_service.get(db, connection_id, project_id)
    installation = await github_installation_service.require_for_project(db, project_id)

    tc = await get_temporal_client()
    try:
        await tc.start_workflow(
            GithubSyncWorkflow.run,
            args=[
                str(connection.id),
                str(project_id),
                installation.installation_id,
                connection.repo_full_name,
                connection.default_branch,
                "refresh",
            ],
            id=f"gh-sync-{connection.id}",
            task_queue=TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError:
        raise HTTPException(status_code=409, detail="A sync is already in progress")

    connection.sync_status = "pending"
    await db.commit()
    await db.refresh(connection)
    return connection


@router.delete(
    "/{project_id}/github/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_repo(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await github_connection_service.delete(db, connection_id, project_id)
