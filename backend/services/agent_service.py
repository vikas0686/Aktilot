import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models.agent import Agent


async def create(
    db: AsyncSession,
    project_id: uuid.UUID,
    name: str,
    description: str | None,
    system_prompt: str,
    top_k: int = 2,
) -> Agent:
    agent = Agent(
        project_id=project_id,
        name=name,
        description=description,
        system_prompt=system_prompt,
        top_k=top_k,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def list_for_project(db: AsyncSession, project_id: uuid.UUID) -> list[Agent]:
    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(Agent.created_at.asc())
    )
    return list(result.scalars().all())


async def get(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def update(
    db: AsyncSession,
    agent_id: uuid.UUID,
    name: str | None,
    description: str | None,
    system_prompt: str | None,
    top_k: int | None = None,
) -> Agent:
    agent = await get(db, agent_id)
    if name is not None:
        agent.name = name
    if description is not None:
        agent.description = description
    if system_prompt is not None:
        agent.system_prompt = system_prompt
    if top_k is not None:
        agent.top_k = top_k
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete(db: AsyncSession, agent_id: uuid.UUID) -> None:
    agent = await get(db, agent_id)
    await db.delete(agent)
    await db.commit()


async def get_by_share_slug(db: AsyncSession, share_slug: str) -> Agent:
    result = await db.execute(select(Agent).where(Agent.share_slug == share_slug))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Shared agent link not found")
    return agent


async def generate_share_link(
    db: AsyncSession, agent_id: uuid.UUID, daily_message_cap: int | None
) -> Agent:
    agent = await get(db, agent_id)
    agent.share_slug = secrets.token_urlsafe(24)
    agent.share_daily_message_cap = (
        daily_message_cap or settings.share_default_daily_message_cap
    )
    # The daily cap only counts messages from this point forward — otherwise
    # lowering the cap would retroactively block on usage from before the
    # change, since messages/sessions aren't tied to a particular share_slug.
    agent.share_daily_cap_reset_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(agent)
    return agent


async def revoke_share_link(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await get(db, agent_id)
    agent.share_slug = None
    await db.commit()
    await db.refresh(agent)
    return agent
