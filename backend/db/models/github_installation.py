import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class GithubInstallation(Base):
    __tablename__ = "github_installations"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    installation_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    account_login: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="github_installation"
    )
    connections: Mapped[list["GithubConnection"]] = relationship(  # noqa: F821
        "GithubConnection",
        back_populates="installation",
        cascade="all, delete-orphan",
    )
