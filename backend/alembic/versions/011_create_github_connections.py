"""create github_connections table

Revision ID: 011
Revises: 010
Create Date: 2026-07-20 00:01:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("installation_id", sa.UUID(), nullable=False),
        sa.Column("repo_full_name", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False),
        sa.Column(
            "sync_status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["github_installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "repo_full_name", name="uq_github_connection_repo"
        ),
    )
    op.create_index(
        "ix_github_connections_project_id", "github_connections", ["project_id"]
    )
    op.create_index(
        "ix_github_connections_installation_id",
        "github_connections",
        ["installation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_github_connections_installation_id", table_name="github_connections"
    )
    op.drop_index("ix_github_connections_project_id", table_name="github_connections")
    op.drop_table("github_connections")
