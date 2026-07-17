import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.schemas import ShareLinkCreate, ShareLinkResponse
from services import agent_service

router = APIRouter(prefix="/api/agents", tags=["agent-share"])


def _to_response(agent) -> ShareLinkResponse:
    return ShareLinkResponse(
        share_slug=agent.share_slug,
        share_path=f"/share/{agent.share_slug}",
        daily_message_cap=agent.share_daily_message_cap,
    )


@router.post("/{agent_id}/share", response_model=ShareLinkResponse)
async def create_or_regenerate_share_link(
    agent_id: uuid.UUID,
    body: ShareLinkCreate,
    db: AsyncSession = Depends(get_db),
):
    """Generate a new public share link, replacing any existing one.

    Regenerating immediately invalidates the previous link — visitors who
    still have it will get a 404 from the public routes.
    """
    agent = await agent_service.generate_share_link(
        db, agent_id, body.daily_message_cap
    )
    return _to_response(agent)


@router.delete("/{agent_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_link(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await agent_service.revoke_share_link(db, agent_id)
