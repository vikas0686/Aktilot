import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.github_installation import GithubInstallation


async def get_for_project(
    db: AsyncSession, project_id: uuid.UUID
) -> GithubInstallation | None:
    result = await db.execute(
        select(GithubInstallation).where(GithubInstallation.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def require_for_project(
    db: AsyncSession, project_id: uuid.UUID
) -> GithubInstallation:
    installation = await get_for_project(db, project_id)
    if installation is None:
        raise HTTPException(
            status_code=404, detail="No GitHub installation connected for this project"
        )
    return installation


async def upsert(
    db: AsyncSession,
    project_id: uuid.UUID,
    installation_id: int,
    account_login: str,
    account_type: str,
) -> GithubInstallation:
    existing = await get_for_project(db, project_id)
    if existing is not None:
        existing.installation_id = installation_id
        existing.account_login = account_login
        existing.account_type = account_type
        await db.commit()
        await db.refresh(existing)
        return existing

    record = GithubInstallation(
        project_id=project_id,
        installation_id=installation_id,
        account_login=account_login,
        account_type=account_type,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def delete(db: AsyncSession, installation: GithubInstallation) -> None:
    # Cascades to github_connections in Postgres; caller is responsible for
    # clearing each connection's Chroma chunks and calling the GitHub API to
    # uninstall the App before this runs.
    await db.delete(installation)
    await db.commit()
