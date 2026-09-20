# ====== Code Summary ======
# add collection.indexed_signature (nullable VARCHAR(64)) — the indexed-config baseline needs_reindex
# is DERIVED against.
#
# Revision: a3f9c2e1d7b4
# Revises: d4b8f2a1c6e7
# Created: 2026-09-20 00:00:02.000000
#
# Replaces the broken sticky one-way ``needs_reindex`` boolean with a derived flag: the worker stamps
# ``indexed_signature`` (the CollectionIndexSignature the currently-indexed vectors were produced
# under) at the ingestion edge, and every config write recomputes
# ``needs_reindex = (indexed_signature IS NOT NULL AND current_signature != indexed_signature)``.
# NULL = never indexed (nothing stale to reindex). It matches the model's
# ``mapped_column(String(64), nullable=True, server_default=None)`` declaration.
#
# Data safety: SAFE. The column is added nullable with no default, so every existing collection reads
# NULL (never-indexed baseline) until its next successful ingestion advances it — no reindex is
# spuriously flagged on legacy rows. The downgrade drops the column verbatim (faithful reversal).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "a3f9c2e1d7b4"
down_revision = "d4b8f2a1c6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable ``collection.indexed_signature`` baseline column."""
    op.add_column(
        "collection",
        sa.Column("indexed_signature", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Drop ``collection.indexed_signature``, restoring the previous shape exactly."""
    op.drop_column("collection", "indexed_signature")
