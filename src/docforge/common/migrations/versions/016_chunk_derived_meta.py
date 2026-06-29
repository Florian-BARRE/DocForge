"""Add chunk.derived_meta for S5b (LLM-generated metadata) output.

Revision ID: 016
Revises: 015
Create Date: 2026-06-28

The new S5b "metagen" stage runs after S5 and uses an LLM to generate derived metadata per chunk
(atomic propositions, keywords, summary, entities…). Those chunk-scope generated values are stored
on the chunk itself so retrieval can read them (``resolve_field_text`` consults ``derived_meta``
ahead of the document-scope ``doc_meta`` fallback). Document-scope generated values are merged into
``doc_meta`` instead and are NOT stored here.

- ADD ``chunk.derived_meta`` (JSONB, NOT NULL, DEFAULT ``'{}'``) — a per-chunk map of
  ``{generated_field_name: value}``. Empty object means no generated metadata (the default for every
  pre-S5b chunk and for any pipeline with an empty ``metagen.targets`` list).
- ADD a GIN index ``ix_chunk_derived_meta`` on the JSONB column. It is created now (rather than later)
  so future containment/key filters (``derived_meta @> '{...}'`` / ``? key``) on generated fields are
  indexed from day one. GIN on a column that is ``'{}'`` for existing rows is cheap to build.

Data safety:
- The ADD is purely additive and backward-compatible: NOT NULL is safe because of the
  ``DEFAULT '{}'`` server default — every existing chunk row is backfilled to an empty JSON object
  in place by PostgreSQL, no separate UPDATE needed.
- Fully reversible: ``downgrade()`` drops the GIN index then the column. Dropping the column discards
  any generated metadata that S5b had written — acceptable, as it is a derived (re-generatable)
  annotation, never a source of truth (the IR remains canonical).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers — used by Alembic to order migrations.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the chunk.derived_meta JSONB column and its GIN index."""
    # 1. Per-chunk generated-metadata map (NOT NULL via the '{}' server default — safe on existing rows)
    op.add_column(
        "chunk",
        sa.Column(
            "derived_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    # 2. GIN index — enables future containment/key filtering on generated fields (cheap to build now
    #    while every existing row is the empty object)
    op.create_index(
        "ix_chunk_derived_meta",
        "chunk",
        ["derived_meta"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop the GIN index then the derived_meta column (reverse order of creation)."""
    # 1. Drop the index before the column it depends on
    op.drop_index("ix_chunk_derived_meta", table_name="chunk")

    # 2. Drop the column (discards generated metadata — derived data, never a source of truth)
    op.drop_column("chunk", "derived_meta")
