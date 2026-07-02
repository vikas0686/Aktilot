"""create chat_sessions table and messages.session_id

Revision ID: 006
Revises: 005
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_agent_id", "chat_sessions", ["agent_id"])

    op.add_column("messages", sa.Column("session_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_messages_session_id",
        "messages",
        "chat_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_constraint("fk_messages_session_id", "messages", type_="foreignkey")
    op.drop_column("messages", "session_id")
    op.drop_index("ix_chat_sessions_agent_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
