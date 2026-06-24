"""Convert JSON columns to JSONB and add GIN indexes for efficient metadata queries.

Revision ID: 002
Revises: 001
Create Date: 2026-06-12

PostgreSQL GIN indexes only work on JSONB, not JSON. This migration first alters
the three JSON columns to JSONB (lossless — JSONB is a strict superset of JSON in
terms of data representation), then creates GIN indexes on them.

GIN indexes enable containment queries (@>, ?) on JSONB columns — needed for
P5 metadata filtering (user_meta, implicit_meta) and block type_data lookups.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Convert JSON → JSONB, then add GIN indexes on the three metadata columns.

    GIN (Generalized Inverted Index) is the correct index type for JSONB containment
    operators (@>, ?) and is required for sub-linear query performance on large datasets.
    """
    # 1. Alter document.user_meta from JSON to JSONB (required for GIN indexing)
    op.alter_column(
        "document",
        "user_meta",
        type_=sa.dialects.postgresql.JSONB(),
        postgresql_using="user_meta::jsonb",
    )

    # 2. Alter document.implicit_meta from JSON to JSONB
    op.alter_column(
        "document",
        "implicit_meta",
        type_=sa.dialects.postgresql.JSONB(),
        postgresql_using="implicit_meta::jsonb",
    )

    # 3. Alter block.type_data from JSON to JSONB
    op.alter_column(
        "block",
        "type_data",
        type_=sa.dialects.postgresql.JSONB(),
        postgresql_using="type_data::jsonb",
    )

    # 4. GIN index on document.user_meta for user metadata filter queries
    op.create_index(
        index_name="ix_document_user_meta_gin",
        table_name="document",
        columns=["user_meta"],
        postgresql_using="gin",
    )

    # 5. GIN index on document.implicit_meta for system metadata filter queries
    op.create_index(
        index_name="ix_document_implicit_meta_gin",
        table_name="document",
        columns=["implicit_meta"],
        postgresql_using="gin",
    )

    # 6. GIN index on block.type_data for type-specific field queries
    op.create_index(
        index_name="ix_block_type_data_gin",
        table_name="block",
        columns=["type_data"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove GIN indexes and revert JSONB columns back to JSON."""
    # 1. Drop indexes first (in reverse creation order)
    op.drop_index("ix_block_type_data_gin", table_name="block")
    op.drop_index("ix_document_implicit_meta_gin", table_name="document")
    op.drop_index("ix_document_user_meta_gin", table_name="document")

    # 2. Revert columns to JSON
    op.alter_column("block", "type_data", type_=sa.JSON(), postgresql_using="type_data::json")
    op.alter_column("document", "implicit_meta", type_=sa.JSON(), postgresql_using="implicit_meta::json")
    op.alter_column("document", "user_meta", type_=sa.JSON(), postgresql_using="user_meta::json")
