"""Add observability columns to the job table (Brique A).

Revision ID: 009
Revises: 008
Create Date: 2026-06-23

Brique A (resource/job monitoring) needs per-job execution telemetry that the original P2
``job`` table did not capture: which worker ran it, when it started/finished, how many retry
attempts it took, and a coarse live progress signal for the UI.

All columns are additive and nullable-or-defaulted so existing rows stay valid without backfill:
- ``worker_id``      NULL for jobs that were never claimed (pending) or predate this migration.
- ``started_at`` /   NULL until the worker transitions the job to ``running`` / a terminal state.
  ``finished_at``
- ``attempt``        defaults to 1 (single attempt) — server_default keeps old rows consistent.
- ``current_stage``  NULL when no stage is in flight.
- ``progress``       defaults to 0 (not started).

No index is added: monitoring queries filter on the already-present ``status`` / ``collection_id``
columns. Add ``ix_job_status`` later only if profiling shows a need.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the six additive observability columns to ``job``."""
    # 1. Worker attribution + execution window (all nullable — unclaimed/legacy rows stay valid)
    op.add_column("job", sa.Column("worker_id", sa.String(length=64), nullable=True))
    op.add_column("job", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Retry counter — server_default '1' so existing rows read back as a single attempt
    op.add_column(
        "job",
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default="1"),
    )

    # 3. Live progress signal — current stage node id + 0–100 percent (default 0 = not started)
    op.add_column("job", sa.Column("current_stage", sa.String(length=64), nullable=True))
    op.add_column(
        "job",
        sa.Column("progress", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Drop the observability columns in reverse order of addition."""
    # 1. Reverse the additions
    op.drop_column("job", "progress")
    op.drop_column("job", "current_stage")
    op.drop_column("job", "attempt")
    op.drop_column("job", "finished_at")
    op.drop_column("job", "started_at")
    op.drop_column("job", "worker_id")
