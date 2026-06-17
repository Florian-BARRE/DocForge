"""Add chunk.parent_id for hierarchical (parent/child) chunking.

Revision ID: 008
Revises: 007
Create Date: 2026-06-16

Hierarchical chunking (Axe 1) emits one parent chunk per section over its child chunks.
Children are the units indexed in Qdrant and matched at search time; the parent carries the
full section text and is returned for context. ``parent_id`` is a nullable self-reference:
- NULL  → a flat chunk (default mode) or a parent (section) chunk.
- set   → a child chunk pointing at its section parent.
A self FK with ON DELETE CASCADE keeps children from outliving their parent.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add the nullable ``parent_id`` self-reference column and its lookup index.

    - ``parent_id`` references ``chunk.id``; deleting a parent cascades to its children so a
      reindex that drops a document's chunks never leaves orphaned children behind.
    - The partial index covers only rows where ``parent_id`` is set (children), which is the
      sole access pattern (fetch a parent's children / roll a child up to its parent).
    """
    # 1. Add the self-referencing parent_id column (nullable — flat chunks have no parent)
    op.add_column("chunk", sa.Column("parent_id", sa.UUID(), nullable=True))

    # 2. Self FK with cascade delete — children never outlive their parent chunk
    op.create_foreign_key(
        "fk_chunk_parent_id",
        "chunk",
        "chunk",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 3. Partial index on set parent_id — the only query path that touches this column
    op.create_index(
        "ix_chunk_parent_id",
        "chunk",
        ["parent_id"],
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the parent_id index, FK, and column (reverse order of creation)."""
    # 1. Drop the index, then the FK, then the column
    op.drop_index("ix_chunk_parent_id", table_name="chunk")
    op.drop_constraint("fk_chunk_parent_id", "chunk", type_="foreignkey")
    op.drop_column("chunk", "parent_id")
