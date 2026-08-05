# ====== Code Summary ======
# add job observability breadcrumbs + worker heartbeat table
#
# Revision: a7b4c9e2f1d3
# Revises: f6a3d8b2c1e7
# Created: 2026-08-05 00:00:00.000000
#
# Deepens job/worker observability with three additive changes: (1) a per-item fan-out counter on
# ``job`` (items_done / items_total, tracking the current foreach root stage), plus a structured
# failure breadcrumb (failed_node_id / failed_node_kind / failed_item_index / error_type) that
# complements the existing free-text ``error``; (2) a ``node_kind`` label on ``job_stage_event`` so a
# stage row records what kind of node it was (action/group/foreach or the concrete kind); (3) a new
# ``worker_heartbeats`` table so an idle-but-alive worker is observable and a dead worker is
# detectable independently of the job-stall reaper.
#
# Data safety: STRICTLY ADDITIVE and safe online. Every new column is nullable, so pre-existing rows
# backfill to NULL with no rewrite. The new table is empty on creation. Nothing is dropped, renamed,
# or retyped. The downgrade removes exactly what the upgrade added — the seven columns and the table —
# discarding only observability data that the worker re-emits on the next run (no source-of-truth loss).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "a7b4c9e2f1d3"
down_revision = "f6a3d8b2c1e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the fan-out counter, failure breadcrumb, stage node_kind, and worker_heartbeats table."""
    # 1. Per-item fan-out counter on job (NULL when the current root stage is not a foreach).
    op.add_column("job", sa.Column("items_done", sa.SmallInteger(), nullable=True))
    op.add_column("job", sa.Column("items_total", sa.SmallInteger(), nullable=True))

    # 2. Structured failure breadcrumb on job (NULL until the job fails).
    op.add_column("job", sa.Column("failed_node_id", sa.String(length=128), nullable=True))
    op.add_column("job", sa.Column("failed_node_kind", sa.String(length=64), nullable=True))
    op.add_column("job", sa.Column("failed_item_index", sa.SmallInteger(), nullable=True))
    op.add_column("job", sa.Column("error_type", sa.String(length=128), nullable=True))

    # 3. Stage type label on job_stage_event (NULL for rows written before this column).
    op.add_column("job_stage_event", sa.Column("node_kind", sa.String(length=64), nullable=True))

    # 4. Worker liveness heartbeat table (worker_id PK; both timestamps NOT NULL).
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=64), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_id", name=op.f("pk_worker_heartbeats")),
    )


def downgrade() -> None:
    """Drop the worker_heartbeats table and the added job / job_stage_event columns."""
    op.drop_table("worker_heartbeats")
    op.drop_column("job_stage_event", "node_kind")
    op.drop_column("job", "error_type")
    op.drop_column("job", "failed_item_index")
    op.drop_column("job", "failed_node_kind")
    op.drop_column("job", "failed_node_id")
    op.drop_column("job", "items_total")
    op.drop_column("job", "items_done")
