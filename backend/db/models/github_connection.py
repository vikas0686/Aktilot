import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class GithubConnection(Base):
    __tablename__ = "github_connections"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "repo_full_name", name="uq_github_connection_repo"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("github_installations.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_full_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # pending | syncing | synced | error
    sync_status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default="pending"
    )
    file_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="github_connections"
    )
    installation: Mapped["GithubInstallation"] = relationship(  # noqa: F821
        "GithubInstallation", back_populates="connections"
    )
