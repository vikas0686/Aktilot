import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.schemas import ChatRequest, ChatResponse, MessageResponse
from services import agent_rag_service, message_service, agent_service

router = APIRouter(prefix="/api/agents", tags=["chat"])


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat(
    agent_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    return await agent_rag_service.chat(db, agent_id, body.question)


@router.get("/{agent_id}/messages", response_model=list[MessageResponse])
async def get_messages(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await agent_service.get(db, agent_id)  # 404 if agent missing
    return await message_service.list_for_agent(db, agent_id)
