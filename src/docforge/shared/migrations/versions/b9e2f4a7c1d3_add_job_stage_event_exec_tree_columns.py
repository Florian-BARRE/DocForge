# ====== Code Summary ======
# add job_stage_event execution-tree columns (materialized-path model + scored-node score)
#
# Revision: b9e2f4a7c1d3
# Revises: a1d4f7b2c9e0
# Created: 2026-09-07 00:00:00.000000
#
# Adds five nullable ``job_stage_event`` columns so the worker can persist the FULL per-node execution
# tree — every node, including nested group children and per-item ForEach body instances — instead of
# only the flat per-root-stage timeline. The tree is modelled as a MATERIALIZED PATH (no self-FK): root
# rows are the existing live rows, nested rows are inserted post-run, and the UI reconstructs the tree
# from the path string + depth. Columns:
#   - ``node_path`` (TEXT NULL) — materialized path of the node (root = bare node id ``parse``; nested =
#     dotted/bracketed path ``enrich.figures[3].vlm``); NULL = legacy row (API falls back to ``stage``).
#   - ``depth`` (INTEGER NULL) — 0 = root stage, larger = more nested; NULL = legacy (treated as 0).
#   - ``parent_path`` (TEXT NULL) — ``node_path`` of the parent; NULL for roots and legacy rows.
#   - ``item_index`` (INTEGER NULL) — ForEach item index when this row is a per-item body instance, else
#     NULL.
#   - ``score`` (DOUBLE PRECISION NULL) — quality score of a ``scored``-family node, in [0, 1]; NULL for
#     non-scored nodes and legacy rows. Stored as Float (not Numeric like ``cost_usd``): a [0, 1] quality
#     score needs no exact-decimal representation, unlike money.
# Purely additive.
#
# Data safety: SAFE ONLINE. Every column is nullable with NO server_default, so adding them is a
# metadata-only change on PostgreSQL (no table rewrite, only a brief ACCESS EXCLUSIVE lock) and needs no
# backfill: pre-existing rows stay NULL, which the read side treats as a legacy flat-timeline row.
# The downgrade drops the five columns in reverse add order, restoring the prior column shape verbatim;
# it loses only the recorded execution-tree structure and node scores, all advisory read-side metadata
# with no downstream dependency.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b9e2f4a7c1d3"
down_revision = "a1d4f7b2c9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the five nullable job_stage_event execution-tree columns."""
    op.add_column("job_stage_event", sa.Column("node_path", sa.Text(), nullable=True))
    op.add_column("job_stage_event", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column("job_stage_event", sa.Column("parent_path", sa.Text(), nullable=True))
    op.add_column("job_stage_event", sa.Column("item_index", sa.Integer(), nullable=True))
    op.add_column("job_stage_event", sa.Column("score", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop the five columns in reverse add order, restoring the prior column shape verbatim."""
    op.drop_column("job_stage_event", "score")
    op.drop_column("job_stage_event", "item_index")
    op.drop_column("job_stage_event", "parent_path")
    op.drop_column("job_stage_event", "depth")
    op.drop_column("job_stage_event", "node_path")
