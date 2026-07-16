import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    top_k: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Public share link: NULL means sharing is disabled for this agent.
    share_slug: Mapped[str | None] = mapped_column(
        sa.String(64), unique=True, nullable=True, index=True
    )
    # Hard daily cap on visitor-originated messages while share_slug is set.
    share_daily_message_cap: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    # Set every time the share link is (re)generated. The daily cap only
    # counts messages from this point forward, so lowering the cap never
    # retroactively blocks on usage that happened under a higher/older cap.
    share_daily_cap_reset_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    project: Mapped["Project"] = relationship("Project", back_populates="agents")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        "Message", back_populates="agent", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(  # noqa: F821
        "ChatSession", back_populates="agent", cascade="all, delete-orphan"
    )
