# ====== Code Summary ======
# add per-collection execution-trace verbosity
#
# Revision: c5d9f2a8b3e1
# Revises: a4f1c8e7b2d6
# Created: 2026-09-07 00:00:00.000000
#
# Adds one non-nullable column ``trace_verbosity`` (String(16)) to ``collection``, defaulting to
# ``"shape"``. It selects how much of each node's input/output an ingestion run captures onto the job
# stage timeline: ``"shape"`` keeps only the cheap inline shape summary, ``"full"`` additionally stores
# the raw payload in the object store (opt-in, clamped by the operator ceiling
# WORKER_TRACE_MAX_VERBOSITY). Pairs with the six ``job_stage_event`` trace columns added in
# a4f1c8e7b2d6 (this is the per-collection knob that drives whether those columns get a full-payload ref).
#
# Data safety: SAFE ONLINE + STRICTLY ADDITIVE. The column is NOT NULL but carries a ``"shape"`` server
# default, so every pre-existing collection row backfills to ``"shape"`` (today's behaviour — no raw
# content at rest) without a separate UPDATE pass, and the add stays a metadata-only change (no table
# rewrite). No existing column is dropped, renamed, or retyped. The downgrade drops the column verbatim,
# discarding any per-collection ``full`` opt-in (a plain, reversible schema-only change).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "c5d9f2a8b3e1"
down_revision = "a4f1c8e7b2d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the non-nullable per-collection trace-verbosity column (existing rows → "shape")."""
    op.add_column(
        "collection",
        sa.Column(
            "trace_verbosity",
            sa.String(length=16),
            nullable=False,
            server_default="shape",
        ),
    )


def downgrade() -> None:
    """Drop the per-collection trace-verbosity column, reverting to the shape-only default."""
    op.drop_column("collection", "trace_verbosity")
