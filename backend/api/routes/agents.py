import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.schemas import AgentCreate, AgentResponse, AgentUpdate
from services import agent_service, project_service

# Project-scoped: create + list
project_router = APIRouter(prefix="/api/projects", tags=["agents"])

# Agent-scoped: get + update + delete
agent_router = APIRouter(prefix="/api/agents", tags=["agents"])


@project_router.post(
    "/{project_id}/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    project_id: uuid.UUID,
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    await project_service.get(db, project_id)  # 404 if project missing
    return await agent_service.create(
        db, project_id, body.name, body.description, body.system_prompt, body.top_k
    )


@project_router.get("/{project_id}/agents", response_model=list[AgentResponse])
async def list_agents(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await project_service.get(db, project_id)
    return await agent_service.list_for_project(db, project_id)


@agent_router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await agent_service.get(db, agent_id)


@agent_router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await agent_service.update(
        db, agent_id, body.name, body.description, body.system_prompt, body.top_k
    )


@agent_router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await agent_service.delete(db, agent_id)
