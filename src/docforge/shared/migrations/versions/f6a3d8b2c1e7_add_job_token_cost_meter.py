# ====== Code Summary ======
# add per-stage + per-job token/cost meter columns
#
# Revision: f6a3d8b2c1e7
# Revises: e5c2b8f4a1d9
# Created: 2026-08-02 00:00:00.000000
#
# Adds the paid text-gen (LLM/VLM/structgen) token + USD cost meter to observability: three nullable
# columns on ``job_stage_event`` (per-stage tokens + cost, NULL when a stage made no paid call) and
# three running-total columns on ``job`` (the per-document lifetime tokens + cost). The worker sums a
# stage's usage from the execution tree at each stage end and increments the job aggregate.
#
# Data safety: STRICTLY ADDITIVE. The stage columns are nullable, backfilling to NULL. The job
# aggregate columns are NOT NULL with a server default of 0, so every pre-existing job row backfills
# to a zero meter without a separate UPDATE pass. No existing column is dropped, renamed, or retyped.
# The downgrade drops the six columns, discarding the recorded meter (recomputable only by re-ingest).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "f6a3d8b2c1e7"
down_revision = "e5c2b8f4a1d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the per-stage and per-job token/cost meter columns (existing rows → NULL / zero meter)."""
    op.add_column("job_stage_event", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("job_stage_event", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("job_stage_event", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))
    op.add_column(
        "job",
        sa.Column("total_prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "job",
        sa.Column("total_completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "job", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0")
    )


def downgrade() -> None:
    """Drop the token/cost meter columns, reverting to the pre-meter schema."""
    op.drop_column("job", "cost_usd")
    op.drop_column("job", "total_completion_tokens")
    op.drop_column("job", "total_prompt_tokens")
    op.drop_column("job_stage_event", "cost_usd")
    op.drop_column("job_stage_event", "completion_tokens")
    op.drop_column("job_stage_event", "prompt_tokens")
