import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models.agent import Agent
from db.models.chat_session import ChatSession
from db.models.message import Message

_TITLE_MAX_LEN = 60


async def create(db: AsyncSession, agent_id: uuid.UUID) -> ChatSession:
    """Create an admin-app session (visitor_id is NULL)."""
    session = ChatSession(agent_id=agent_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_for_agent(db: AsyncSession, agent_id: uuid.UUID) -> list[ChatSession]:
    """Sessions visible in the authenticated admin app only.

    Anonymous visitor sessions are excluded — no admin/creator view is ever
    allowed to surface a visitor's conversation.
    """
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.agent_id == agent_id, ChatSession.visitor_id.is_(None))
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get(db: AsyncSession, session_id: uuid.UUID) -> ChatSession:
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


# ── Public share-link (anonymous visitor) sessions ────────────────────────────


async def create_for_visitor(
    db: AsyncSession, agent_id: uuid.UUID, visitor_id: uuid.UUID
) -> ChatSession:
    session = ChatSession(agent_id=agent_id, visitor_id=visitor_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_for_agent_and_visitor(
    db: AsyncSession, agent_id: uuid.UUID, visitor_id: uuid.UUID
) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.agent_id == agent_id, ChatSession.visitor_id == visitor_id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_for_visitor(
    db: AsyncSession, session_id: uuid.UUID, agent_id: uuid.UUID, visitor_id: uuid.UUID
) -> ChatSession:
    """Fetch a session, scoped to both the agent and the requesting visitor.

    Returns 404 (not 403) on any mismatch so a guess can't distinguish
    "wrong visitor" from "session doesn't exist".
    """
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.agent_id == agent_id,
            ChatSession.visitor_id == visitor_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


async def count_visitor_messages_since(
    db: AsyncSession, visitor_id: uuid.UUID, agent_id: uuid.UUID, since: datetime
) -> int:
    result = await db.execute(
        select(func.count(Message.id))
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(
            ChatSession.visitor_id == visitor_id,
            ChatSession.agent_id == agent_id,
            Message.role == "user",
            Message.created_at >= since,
        )
    )
    return result.scalar_one()


async def count_agent_visitor_messages_since(
    db: AsyncSession, agent_id: uuid.UUID, since: datetime
) -> int:
    result = await db.execute(
        select(func.count(Message.id))
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(
            ChatSession.agent_id == agent_id,
            ChatSession.visitor_id.is_not(None),
            Message.role == "user",
            Message.created_at >= since,
        )
    )
    return result.scalar_one()


async def reserve_daily_share_slot(
    db: AsyncSession, agent_id: uuid.UUID, window_start: datetime, daily_cap: int
) -> bool:
    """Atomically claim one slot against the agent's rolling daily visitor-message
    cap, before the caller starts the (slow) chat workflow.

    A plain "COUNT then decide" check has a race: concurrent requests can all
    read a count below the cap before any of their messages are persisted,
    letting them all through. This folds the same count (mirroring
    count_agent_visitor_messages_since) into the WHERE clause of a guarded
    UPDATE instead: the UPDATE takes a row lock on the agent, so a second
    concurrent reservation blocks until the first commits, then re-evaluates
    the count against the now-updated reserved total. Returns False if the
    cap has already been reached.
    """
    persisted_count = (
        select(func.count(Message.id))
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(
            ChatSession.agent_id == agent_id,
            ChatSession.visitor_id.is_not(None),
            Message.role == "user",
            Message.created_at >= window_start,
        )
        .scalar_subquery()
    )
    result = await db.execute(
        sa_update(Agent)
        .where(
            Agent.id == agent_id,
            Agent.share_daily_reserved_count + persisted_count < daily_cap,
        )
        .values(share_daily_reserved_count=Agent.share_daily_reserved_count + 1)
        .returning(Agent.id)
    )
    claimed = result.scalar_one_or_none() is not None
    await db.commit()
    return claimed


async def release_daily_share_slot(db: AsyncSession, agent_id: uuid.UUID) -> None:
    """Release a reservation from reserve_daily_share_slot, once the request
    that claimed it has either persisted its message or failed."""
    await db.execute(
        sa_update(Agent)
        .where(Agent.id == agent_id)
        .values(share_daily_reserved_count=Agent.share_daily_reserved_count - 1)
    )
    await db.commit()


async def purge_expired_visitor_sessions(
    db: AsyncSession, retention_days: int | None = None
) -> int:
    """Delete anonymous visitor sessions (and their messages, via FK cascade)
    that have had no activity for `retention_days`. Returns rows deleted."""
    days = retention_days or settings.share_visitor_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        sa_delete(ChatSession)
        .where(ChatSession.visitor_id.is_not(None), ChatSession.updated_at < cutoff)
        .returning(ChatSession.id)
    )
    deleted_ids = result.scalars().all()
    await db.commit()
    return len(deleted_ids)


async def touch_with_title(
    db: AsyncSession, session_id: uuid.UUID, question: str
) -> None:
    session = await get(db, session_id)
    if session.title is None:
        title = question.strip()
        session.title = (
            title[:_TITLE_MAX_LEN] + "…" if len(title) > _TITLE_MAX_LEN else title
        )
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
