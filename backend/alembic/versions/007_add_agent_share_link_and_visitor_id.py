"""add agent share link fields and chat_sessions.visitor_id

Revision ID: 007
Revises: 006
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("share_slug", sa.String(64), nullable=True))
    op.create_index(
        "ix_agents_share_slug", "agents", ["share_slug"], unique=True
    )
    op.add_column(
        "agents", sa.Column("share_daily_message_cap", sa.Integer(), nullable=True)
    )

    op.add_column(
        "chat_sessions", sa.Column("visitor_id", sa.UUID(), nullable=True)
    )
    op.create_index(
        "ix_chat_sessions_visitor_id", "chat_sessions", ["visitor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_visitor_id", table_name="chat_sessions")
    op.drop_column("chat_sessions", "visitor_id")

    op.drop_column("agents", "share_daily_message_cap")
    op.drop_index("ix_agents_share_slug", table_name="agents")
    op.drop_column("agents", "share_slug")
