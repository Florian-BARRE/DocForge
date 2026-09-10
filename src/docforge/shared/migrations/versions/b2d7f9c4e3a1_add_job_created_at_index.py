# ====== Code Summary ======
# add standalone ix_job_created_at index on job (created_at DESC)
#
# Revision: b2d7f9c4e3a1
# Revises: c5d9f2a8b3e1
# Created: 2026-09-10 00:00:00.000000
#
# Adds a single standalone btree index ``ix_job_created_at`` on ``job (created_at DESC)``. Today only
# collection-leading composites exist (``ix_job_collection_created_at``), so the fleet-wide "All Jobs"
# listing — which orders by ``created_at`` with no collection filter — falls back to a seq-scan + sort,
# and age-based pruning has no index to lean on. The DESC ordering is expressed via raw text because a
# ``create_index`` column list can't carry a per-column DESC; it matches the model's
# ``Index("ix_job_created_at", text("created_at DESC"))`` declaration exactly. Mirrors the standalone
# ``ix_audit_log_created_at`` pattern from b7d3f1a8c204.
#
# Data safety: SAFE + STRICTLY ADDITIVE. Creating an index neither reads nor mutates row data; no column
# is added, dropped, renamed, or retyped, and no constraint changes. The downgrade drops the index
# verbatim, restoring the previous shape exactly (the pre-existing composites are untouched).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b2d7f9c4e3a1"
down_revision = "c5d9f2a8b3e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the standalone ``created_at DESC`` index backing the fleet-wide job listing + pruning."""
    op.create_index("ix_job_created_at", "job", [sa.text("created_at DESC")], unique=False)


def downgrade() -> None:
    """Drop the standalone ``ix_job_created_at`` index, reverting to the collection-leading composites."""
    op.drop_index("ix_job_created_at", table_name="job")
