"""add agents.share_daily_reserved_count

Revision ID: 009
Revises: 008
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "share_daily_reserved_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "share_daily_reserved_count")
