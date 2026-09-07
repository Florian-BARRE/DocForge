# ====== Code Summary ======
# add job_stage_event trace-payload columns (inline shape summaries + full-payload object-store refs)
#
# Revision: a4f1c8e7b2d6
# Revises: b9e2f4a7c1d3
# Created: 2026-09-07 00:00:00.000000
#
# Adds six nullable ``job_stage_event`` columns so each per-node row can carry a Phase 2 trace payload:
# a cheap, always-inline SHAPE summary of the node's resolved input/output plus an opt-in REFERENCE to
# the full raw payload stored in the object store by content hash (the DB keeps only the reference).
# Columns:
#   - ``input_summary`` / ``output_summary`` (JSONB NULL) — bounded shape descriptor of the node's
#     input/output (e.g. ``{type, fields, sizes, item_count, hash}``); a content hash, never the raw
#     content. NULL when trace capture was off, the node had no input/output, or for legacy rows.
#   - ``input_ref`` / ``output_ref`` (TEXT NULL) — object-store reference (content-hash key) to the FULL
#     raw input/output payload when the collection opted into the full-capture tier; a reference GC'd
#     with the job, not the content. NULL otherwise.
#   - ``has_full_input`` / ``has_full_output`` (BOOLEAN NULL) — whether a full payload was stored, which
#     drives the UI "load payload" affordance. NULL/legacy is false-ish.
# Purely additive.
#
# Data safety: SAFE ONLINE. Every column is nullable with NO server_default, so adding them is a
# metadata-only change on PostgreSQL (no table rewrite, only a brief ACCESS EXCLUSIVE lock) and needs no
# backfill: pre-existing rows stay NULL, which the read side treats as "no trace captured". The downgrade
# drops the six columns in reverse add order, restoring the prior column shape verbatim; it loses only the
# recorded trace summaries and the object-store references (advisory read-side metadata with no downstream
# dependency — the referenced object-store payloads are GC'd independently with the job).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision = "a4f1c8e7b2d6"
down_revision = "b9e2f4a7c1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the six nullable job_stage_event trace-payload columns."""
    op.add_column("job_stage_event", sa.Column("input_summary", postgresql.JSONB(), nullable=True))
    op.add_column("job_stage_event", sa.Column("output_summary", postgresql.JSONB(), nullable=True))
    op.add_column("job_stage_event", sa.Column("input_ref", sa.Text(), nullable=True))
    op.add_column("job_stage_event", sa.Column("output_ref", sa.Text(), nullable=True))
    op.add_column("job_stage_event", sa.Column("has_full_input", sa.Boolean(), nullable=True))
    op.add_column("job_stage_event", sa.Column("has_full_output", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Drop the six columns in reverse add order, restoring the prior column shape verbatim."""
    op.drop_column("job_stage_event", "has_full_output")
    op.drop_column("job_stage_event", "has_full_input")
    op.drop_column("job_stage_event", "output_ref")
    op.drop_column("job_stage_event", "input_ref")
    op.drop_column("job_stage_event", "output_summary")
    op.drop_column("job_stage_event", "input_summary")
