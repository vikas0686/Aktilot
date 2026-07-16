"""add agents.share_daily_cap_reset_at

Revision ID: 008
Revises: 007
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "share_daily_cap_reset_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "share_daily_cap_reset_at")
