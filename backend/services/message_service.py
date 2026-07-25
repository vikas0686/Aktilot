import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.chat_session import ChatSession
from db.models.message import Message


async def create(
    db: AsyncSession,
    agent_id: uuid.UUID,
    role: str,
    content: str,
    session_id: uuid.UUID | None = None,
) -> Message:
    message = Message(
        agent_id=agent_id, session_id=session_id, role=role, content=content
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def list_for_agent(
    db: AsyncSession, agent_id: uuid.UUID, limit: int = 200, offset: int = 0
) -> list[Message]:
    """Messages visible in the authenticated admin app only.

    Messages that belong to an anonymous visitor's chat session are excluded —
    no admin/creator view is ever allowed to surface a visitor's conversation.

    A conversation can grow without bound, so this is paginated from the most
    recent message backwards (limit/offset apply to descending order) and then
    re-sorted ascending for display — offset=0 always returns the most recent
    page of the conversation, not the oldest `limit` messages.
    """
    result = await db.execute(
        select(Message)
        .outerjoin(ChatSession, Message.session_id == ChatSession.id)
        .where(
            Message.agent_id == agent_id,
            or_(Message.session_id.is_(None), ChatSession.visitor_id.is_(None)),
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def list_for_session(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 200, offset: int = 0
) -> list[Message]:
    """See list_for_agent's docstring — same most-recent-page-first pagination
    reversed back to chronological order for display."""
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages
