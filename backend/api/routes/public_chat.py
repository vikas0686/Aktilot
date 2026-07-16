"""Public, unauthenticated routes for shared agent links.

No login, no project/knowledge-base visibility — everything reachable here
is scoped to a single agent (resolved by its public share_slug, never its
internal database id) and to the requesting visitor's own cookie identity.
Nothing in this module imports project_service or exposes project/file data.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_deps import get_visitor_id
from api.routes.agent_chat import run_chat_workflow
from config import settings
from db.session import get_db
from models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    MessageResponse,
    PublicAgentResponse,
)
from services import agent_service, message_service, session_service

router = APIRouter(prefix="/api/public", tags=["public-chat"])


@router.get("/agents/{slug}", response_model=PublicAgentResponse)
async def get_public_agent(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _visitor_id: uuid.UUID = Depends(get_visitor_id),
):
    return await agent_service.get_by_share_slug(db, slug)


@router.post(
    "/agents/{slug}/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_session(
    slug: str,
    db: AsyncSession = Depends(get_db),
    visitor_id: uuid.UUID = Depends(get_visitor_id),
):
    agent = await agent_service.get_by_share_slug(db, slug)
    return await session_service.create_for_visitor(db, agent.id, visitor_id)


@router.get("/agents/{slug}/sessions", response_model=list[ChatSessionResponse])
async def list_public_sessions(
    slug: str,
    db: AsyncSession = Depends(get_db),
    visitor_id: uuid.UUID = Depends(get_visitor_id),
):
    agent = await agent_service.get_by_share_slug(db, slug)
    return await session_service.list_for_agent_and_visitor(db, agent.id, visitor_id)


@router.get(
    "/agents/{slug}/sessions/{session_id}/messages",
    response_model=list[MessageResponse],
)
async def get_public_session_messages(
    slug: str,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    visitor_id: uuid.UUID = Depends(get_visitor_id),
):
    agent = await agent_service.get_by_share_slug(db, slug)
    session = await session_service.get_for_visitor(
        db, session_id, agent.id, visitor_id
    )
    return await message_service.list_for_session(db, session.id)


@router.post("/agents/{slug}/chat", response_model=ChatResponse)
async def public_chat(
    slug: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    visitor_id: uuid.UUID = Depends(get_visitor_id),
):
    agent = await agent_service.get_by_share_slug(db, slug)
    session = await session_service.get_for_visitor(
        db, body.session_id, agent.id, visitor_id
    )

    now = datetime.now(timezone.utc)

    hourly_count = await session_service.count_visitor_messages_since(
        db, visitor_id, agent.id, now - timedelta(hours=1)
    )
    if hourly_count >= settings.share_visitor_hourly_message_cap:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You've reached the message limit for this chat. Please try again in a bit.",
        )

    daily_cap = (
        agent.share_daily_message_cap or settings.share_default_daily_message_cap
    )
    daily_window_start = now - timedelta(days=1)
    reset_at = agent.share_daily_cap_reset_at
    if reset_at is not None:
        # SQLite (used in tests) drops tzinfo on round-trip; Postgres doesn't.
        # Normalize so the comparison below is never naive-vs-aware.
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        if reset_at > daily_window_start:
            # Cap was (re)generated more recently than the rolling 24h window —
            # don't count usage from before that point against the new cap.
            daily_window_start = reset_at
    daily_count = await session_service.count_agent_visitor_messages_since(
        db, agent.id, daily_window_start
    )
    if daily_count >= daily_cap:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This agent has reached its usage limit for today. Please try again later.",
        )

    return await run_chat_workflow(agent.id, session.id, body.question)
