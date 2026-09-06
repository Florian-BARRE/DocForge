# ====== Code Summary ======
# add worker_heartbeats.max_jobs (per-worker configured job capacity)
#
# Revision: b3e8f1a6c204
# Revises: a2f8e1c4d7b9
# Created: 2026-09-06 00:00:00.000000
#
# Adds ``worker_heartbeats.max_jobs`` (INTEGER NULL): the worker's configured arq concurrency, i.e. how
# many ingestion jobs it can run at once. Paired with the live running-job count, it lets the UI render
# "N running / max" per worker. Purely additive.
#
# Data safety: SAFE ONLINE. The column is nullable with NO server_default, so adding it is a
# metadata-only change on PostgreSQL (no table rewrite, no lock beyond a brief ACCESS EXCLUSIVE) and no
# backfill is needed: pre-existing heartbeat rows (and rows from workers on an older build that do not
# report their capacity yet) stay NULL, which the read side treats as "unknown capacity". The downgrade
# drops the column verbatim; it loses only the reported capacities, which the worker re-reports on its
# next heartbeat after a re-upgrade.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b3e8f1a6c204"
down_revision = "a2f8e1c4d7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable worker_heartbeats.max_jobs capacity column."""
    op.add_column(
        "worker_heartbeats",
        sa.Column("max_jobs", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop worker_heartbeats.max_jobs, restoring the prior column shape verbatim."""
    op.drop_column("worker_heartbeats", "max_jobs")
