# ====== Code Summary ======
# drop the dead enrichment_attempt + entity_mention tables
#
# Revision: a2f8e1c4d7b9
# Revises: d1a7c4f8b2e6
# Created: 2026-09-06 00:00:00.000000
#
# Both tables are WRITE-DEAD scaffolding: no producer ever inserted a row. `enrichment_attempt` was
# meant to persist the enrichment escalation chain (one row per model tried) but the enrich pipeline
# never records per-attempt traces; `entity_mention` was meant to hold NER output but no entity
# extractor exists. Their read APIs, export/import row-types and storage-footprint accounting were all
# dead. Both are removed here in one wave.
#
# Data safety: both tables are ALWAYS EMPTY in every deployment (no producer ever wrote a row), so the
# drop cannot lose data. The downgrade recreates each table's structure exactly (empty), matching the
# initial schema, so a rollback restores the schema shape even though there is nothing to restore.
#
# Enum note: `enrichment_attempt.status` uses ``value_enum`` = ``sa.Enum(..., native_enum=False)``, a
# plain VARCHAR with NO Postgres native ENUM type behind it (no CHECK constraint either). So there is
# NO enum type to drop on upgrade or create on downgrade — the column is rendered inline exactly as the
# initial schema and every other migration in this chain does. `entity_mention` has no enum column.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision = "a2f8e1c4d7b9"
down_revision = "d1a7c4f8b2e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the always-empty, never-written enrichment_attempt and entity_mention tables + indexes."""
    op.drop_index(
        op.f("ix_enrichment_attempt_block_enrichment_id"), table_name="enrichment_attempt"
    )
    op.drop_table("enrichment_attempt")
    op.drop_index(op.f("ix_entity_mention_chunk_id"), table_name="entity_mention")
    op.drop_table("entity_mention")


def downgrade() -> None:
    """Recreate both table structures (empty) exactly as the initial schema defined them."""
    # 1. entity_mention — named entities extracted from a chunk (never populated).
    op.create_table(
        "entity_mention",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("surface_text", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.String(length=512), nullable=True),
        sa.Column("span", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunk.id"],
            name=op.f("fk_entity_mention_chunk_id_chunk"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_mention")),
    )
    op.create_index(
        op.f("ix_entity_mention_chunk_id"), "entity_mention", ["chunk_id"], unique=False
    )
    # 2. enrichment_attempt — the enrichment escalation-chain trace (never populated). The status enum
    #    is inline (native_enum=False), matching the initial schema — no separate ENUM type to create.
    op.create_table(
        "enrichment_attempt",
        sa.Column("block_enrichment_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ok", "failed", name="attemptstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["block_enrichment_id"],
            ["block_enrichment.id"],
            name=op.f("fk_enrichment_attempt_block_enrichment_id_block_enrichment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrichment_attempt")),
    )
    op.create_index(
        op.f("ix_enrichment_attempt_block_enrichment_id"),
        "enrichment_attempt",
        ["block_enrichment_id"],
        unique=False,
    )
