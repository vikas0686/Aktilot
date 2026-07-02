import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.schemas import ChatSessionResponse, MessageResponse
from services import agent_service, message_service, session_service

router = APIRouter(prefix="/api", tags=["chat-sessions"])


@router.post(
    "/agents/{agent_id}/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await agent_service.get(db, agent_id)  # 404 if agent missing
    return await session_service.create(db, agent_id)


@router.get("/agents/{agent_id}/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await agent_service.get(db, agent_id)
    return await session_service.list_for_agent(db, agent_id)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    await session_service.get(db, session_id)  # 404 if session missing
    return await message_service.list_for_session(db, session_id)
