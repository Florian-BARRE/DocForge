# ====== Code Summary ======
# add document.warning_reason + document.chunk_count (success-with-warning + denormalized chunk count)
#
# Revision: a1d4f7b2c9e0
# Revises: e2b7f4a9c1d6
# Created: 2026-09-07 00:00:00.000000
#
# Adds two nullable ``document`` columns so a 0-chunk ingestion can be recorded as a SUCCESS-with-warning
# instead of a hard FAILED, and so the corpus grid / overview can show a per-document chunk count:
# ``warning_reason`` (TEXT NULL, a human-readable non-fatal warning surfaced on a persisted document —
# e.g. "ingestion completed but produced 0 chunks — nothing retrievable"; NULL = no warning; distinct
# from ``job.error`` / a FAILED status) and ``chunk_count`` (INTEGER NULL, the number of chunks persisted
# for the document, denormalized to avoid an N+1 COUNT; NULL = unknown / not-yet-recorded for legacy rows,
# 0 = legitimately empty). Purely additive.
#
# Data safety: SAFE ONLINE. Each column is nullable with NO server_default, so adding them is a
# metadata-only change on PostgreSQL (no table rewrite, no lock beyond a brief ACCESS EXCLUSIVE) and no
# backfill is needed: pre-existing document rows stay NULL, which the read side treats as "no warning" and
# "chunk count unknown" respectively. The downgrade drops both columns verbatim, restoring the prior
# column shape exactly; it loses only the recorded warning text and cached chunk counts, both of which are
# advisory read-side metadata with no downstream dependency.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "a1d4f7b2c9e0"
down_revision = "e2b7f4a9c1d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable document.warning_reason and document.chunk_count columns."""
    op.add_column(
        "document",
        sa.Column("warning_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "document",
        sa.Column("chunk_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop both columns, restoring the prior document column shape verbatim."""
    op.drop_column("document", "chunk_count")
    op.drop_column("document", "warning_reason")
