# ====== Code Summary ======
# add worker_heartbeats resource-sampling columns (per-worker live CPU/memory readings)
#
# Revision: e2b7f4a9c1d6
# Revises: c4a8e2f7b169
# Created: 2026-09-06 00:00:00.000000
#
# Adds three nullable ``worker_heartbeats`` columns carrying the worker process's live resource sample,
# written on each heartbeat tick (~10s fresh) so the Monitoring page can show REAL per-worker CPU/memory
# instead of redirecting to Grafana: ``cpu_percent`` (DOUBLE PRECISION NULL, recent CPU utilisation
# percent, may exceed 100 on a multi-core host), ``mem_mb`` (DOUBLE PRECISION NULL, resident memory in
# megabytes) and ``mem_percent`` (DOUBLE PRECISION NULL, resident memory as a percent of host RAM).
# Mirrors the ``max_jobs`` precedent (nullable, no server_default). Purely additive.
#
# Data safety: SAFE ONLINE. Each column is nullable with NO server_default, so adding them is a
# metadata-only change on PostgreSQL (no table rewrite, no lock beyond a brief ACCESS EXCLUSIVE) and no
# backfill is needed: pre-existing heartbeat rows (and rows from workers on an older build that do not
# sample their resources yet) stay NULL, which the read side treats as "unknown / not reported". The
# downgrade drops all three columns verbatim, restoring the prior column shape exactly; it loses only the
# reported samples, which the worker re-reports on its next heartbeat after a re-upgrade.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "e2b7f4a9c1d6"
down_revision = "c4a8e2f7b169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the three nullable worker_heartbeats resource-sampling columns."""
    op.add_column(
        "worker_heartbeats",
        sa.Column("cpu_percent", sa.Float(), nullable=True),
    )
    op.add_column(
        "worker_heartbeats",
        sa.Column("mem_mb", sa.Float(), nullable=True),
    )
    op.add_column(
        "worker_heartbeats",
        sa.Column("mem_percent", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Drop the resource-sampling columns, restoring the prior column shape verbatim."""
    op.drop_column("worker_heartbeats", "mem_percent")
    op.drop_column("worker_heartbeats", "mem_mb")
    op.drop_column("worker_heartbeats", "cpu_percent")
