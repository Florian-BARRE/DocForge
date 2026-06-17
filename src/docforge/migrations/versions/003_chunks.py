"""Add chunk table for S4 (structure-aware chunking) output.

Revision ID: 003
Revises: 002
Create Date: 2026-06-12

The ``chunk`` table is the Postgres source of truth for retrieval units.
Each chunk maps to one Qdrant point (same UUID as primary key) and carries both
raw_text (faithful, for display/citation) and embed_text (augmented, vectorized).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the ``chunk`` table and its indexes.

    - Primary key: ``id`` (UUID) — same value used as Qdrant point ID.
    - ``document_id`` foreign key → CASCADE DELETE keeps Qdrant in sync via application logic.
    - ``config_hash`` enables efficient lookup of chunks produced by a specific chunking config
      (needed for incremental reindex: only re-chunk when S4 params changed).
    - ``block_ids`` (text[]) traces provenance back to specific IR blocks.
    - ``prov`` (jsonb) stores aggregated page/bbox provenance for highlight-on-page features.
    """
    # 1. Create chunk table
    op.create_table(
        "chunk",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column(
            "block_ids",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("embed_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "strategy",
            sa.Text(),
            nullable=False,
            server_default="recursive_structure_aware",
        ),
        sa.Column(
            "prov",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )

    # 2. Index on document_id — primary access pattern: all chunks for a document
    op.create_index("ix_chunk_document_id", "chunk", ["document_id"])

    # 3. Index on config_hash — incremental reindex: find chunks for a given config version
    op.create_index("ix_chunk_config_hash", "chunk", ["config_hash"])

    # 4. Composite index — efficient reindex check: (document_id, config_hash)
    op.create_index(
        "ix_chunk_document_config",
        "chunk",
        ["document_id", "config_hash"],
    )


def downgrade() -> None:
    """Drop the chunk table and all its indexes."""
    # 1. Drop indexes before the table
    op.drop_index("ix_chunk_document_config", table_name="chunk")
    op.drop_index("ix_chunk_config_hash", table_name="chunk")
    op.drop_index("ix_chunk_document_id", table_name="chunk")

    # 2. Drop the table
    op.drop_table("chunk")
