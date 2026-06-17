"""Initial schema: collection, metadata_field, document, block, stage_run, provider_call, job.

Revision ID: 001
Revises:
Create Date: 2026-06-12

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers — used by Alembic to order migrations.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── collection ────────────────────────────────────────────────────────────
    op.create_table(
        "collection",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("supported_formats", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("max_file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=True),
        sa.Column("unknown_field_policy", sa.String(20), nullable=False, server_default="reject"),
        sa.Column("locality_policy", sa.String(30), nullable=False),
        sa.Column("allowed_providers", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("pipeline", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("pipeline_version", sa.String(64), nullable=False, server_default="v1"),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("default_search", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── metadata_field ────────────────────────────────────────────────────────
    op.create_table(
        "metadata_field",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(30), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("filterable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("lexical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("semantic", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("weight_lexical", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("weight_semantic", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("enum_values", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── document ─────────────────────────────────────────────────────────────
    op.create_table(
        "document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_hash", sa.String(64), nullable=False, index=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("format", sa.String(32), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("user_meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("implicit_meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("pipeline_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── block ─────────────────────────────────────────────────────────────────
    op.create_table(
        "block",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("bbox", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.String(128), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("type_data", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_block_document_id", "block", ["document_id"])

    # ── stage_run (P2 node cache) ─────────────────────────────────────────────
    op.create_table(
        "stage_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False, index=True),
        sa.Column("output_ref", sa.String(512), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── provider_call (P2 provider-call cache) ────────────────────────────────
    op.create_table(
        "provider_call",
        sa.Column("call_fp", sa.String(128), primary_key=True),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("provider_version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False, index=True),
        sa.Column("result_ref", sa.String(512), nullable=True),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── job ──────────────────────────────────────────────────────────────────
    op.create_table(
        "job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("budget_spent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("job")
    op.drop_table("provider_call")
    op.drop_table("stage_run")
    op.drop_index("ix_block_document_id", table_name="block")
    op.drop_table("block")
    op.drop_table("document")
    op.drop_table("metadata_field")
    op.drop_table("collection")
