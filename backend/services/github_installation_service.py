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


async def list_reusable_for_project(
    db: AsyncSession, project_id: uuid.UUID
) -> list[GithubInstallation]:
    """Installations already linked to *other* projects — candidates this
    project could attach to instead of going through a fresh GitHub install.
    One row per distinct real GitHub installation_id (first-seen wins),
    excluding whatever installation_id this project is already on (if any)."""
    own = await get_for_project(db, project_id)
    own_installation_id = own.installation_id if own is not None else None

    result = await db.execute(
        select(GithubInstallation).where(GithubInstallation.project_id != project_id)
    )
    seen: dict[int, GithubInstallation] = {}
    for installation in result.scalars():
        if installation.installation_id == own_installation_id:
            continue
        seen.setdefault(installation.installation_id, installation)
    return list(seen.values())


async def is_installation_id_used_elsewhere(
    db: AsyncSession, installation_id: int, excluding_project_id: uuid.UUID
) -> bool:
    """True if some other project still has a GithubInstallation row pointing
    at this same real GitHub installation_id — used to decide whether
    disconnecting is safe to also revoke on GitHub's side."""
    result = await db.execute(
        select(GithubInstallation.id).where(
            GithubInstallation.installation_id == installation_id,
            GithubInstallation.project_id != excluding_project_id,
        )
    )
    return result.first() is not None


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
