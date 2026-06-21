import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.message import Message


async def create(
    db: AsyncSession,
    agent_id: uuid.UUID,
    role: str,
    content: str,
) -> Message:
    message = Message(agent_id=agent_id, role=role, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def list_for_agent(db: AsyncSession, agent_id: uuid.UUID) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.agent_id == agent_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())
