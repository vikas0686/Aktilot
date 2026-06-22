import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError

from db.session import get_db
from models.schemas import (
    ChatRequest,
    ChatResponse,
    MessageResponse,
    RetrievedChunk,
    ToolStep,
)
from services import agent_service, message_service
from temporal.client import get_temporal_client
from temporal.workflows.chat_workflow import TASK_QUEUE, ChatWorkflow

router = APIRouter(prefix="/api/agents", tags=["chat"])


def _unwrap_app_error(exc: WorkflowFailureError) -> ApplicationError | None:
    cause = exc.cause
    if isinstance(cause, ActivityError):
        cause = cause.cause
    return cause if isinstance(cause, ApplicationError) else None


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat(
    agent_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    # Pre-flight: verify agent exists before dispatching to Temporal
    await agent_service.get(db, agent_id)

    tc = await get_temporal_client()
    try:
        result: dict = await tc.execute_workflow(
            ChatWorkflow.run,
            args=[str(agent_id), body.question],
            id=f"chat-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
            execution_timeout=timedelta(minutes=2),
        )
    except WorkflowFailureError as exc:
        app_err = _unwrap_app_error(exc)
        if app_err:
            if app_err.type == "AUTH_ERROR":
                raise HTTPException(
                    401, "Invalid OpenAI API key. Check OPENAI_API_KEY in your .env."
                )
            if app_err.type == "RATE_LIMIT":
                raise HTTPException(
                    429, "OpenAI rate limit exceeded. Try again shortly."
                )
        raise HTTPException(500, "Chat pipeline failed.")

    return ChatResponse(
        answer=result["answer"],
        keywords=result["keywords"],
        retrieved_chunks=[RetrievedChunk(**c) for c in result["chunks"]],
        tool_steps=[
            ToolStep(
                name=s["name"],
                start_time=datetime.fromisoformat(s["start_time"]),
                end_time=datetime.fromisoformat(s["end_time"]),
                duration_ms=s["duration_ms"],
                input_summary=s["input_summary"],
                output_summary=s["output_summary"],
            )
            for s in result["steps"]
        ],
    )


@router.get("/{agent_id}/messages", response_model=list[MessageResponse])
async def get_messages(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await agent_service.get(db, agent_id)  # 404 if agent missing
    return await message_service.list_for_agent(db, agent_id)
