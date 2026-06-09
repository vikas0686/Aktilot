from fastapi import APIRouter
from services import rag_service
from models.schemas import ChatRequest, ChatResponse, ToolStep

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    return await rag_service.chat(req.question)


@router.get("/tools/history", response_model=list[list[ToolStep]])
def tool_history():
    return rag_service.get_tool_history()
