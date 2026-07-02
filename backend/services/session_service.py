import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.chat_session import ChatSession

_TITLE_MAX_LEN = 60


async def create(db: AsyncSession, agent_id: uuid.UUID) -> ChatSession:
    session = ChatSession(agent_id=agent_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_for_agent(db: AsyncSession, agent_id: uuid.UUID) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.agent_id == agent_id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get(db: AsyncSession, session_id: uuid.UUID) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


async def touch_with_title(
    db: AsyncSession, session_id: uuid.UUID, question: str
) -> None:
    session = await get(db, session_id)
    if session.title is None:
        title = question.strip()
        session.title = (
            title[:_TITLE_MAX_LEN] + "…"
            if len(title) > _TITLE_MAX_LEN
            else title
        )
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
