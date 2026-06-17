"""Add config versioning: collection.needs_reindex + config_version table.

Revision ID: 004
Revises: 003
Create Date: 2026-06-15

Supports the config history / rollback endpoints: every config change snapshots the previous
config into ``config_version``.  ``collection.needs_reindex`` flags a collection whose vector
space was invalidated by a config change (e.g. embedding_model change) until a reindex runs.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the needs_reindex flag and the config_version history table."""
    # 1. needs_reindex flag on collection (default false for existing rows)
    op.add_column(
        "collection",
        sa.Column("needs_reindex", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # 2. config_version history table
    op.create_table(
        "config_version",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "collection_id", sa.UUID(),
            sa.ForeignKey("collection.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_config_version_collection_id", "config_version", ["collection_id"])
    op.create_unique_constraint(
        "uq_config_version_collection_version", "config_version", ["collection_id", "version"]
    )


def downgrade() -> None:
    """Drop the config_version table and the needs_reindex column."""
    op.drop_constraint("uq_config_version_collection_version", "config_version", type_="unique")
    op.drop_index("ix_config_version_collection_id", table_name="config_version")
    op.drop_table("config_version")
    op.drop_column("collection", "needs_reindex")
