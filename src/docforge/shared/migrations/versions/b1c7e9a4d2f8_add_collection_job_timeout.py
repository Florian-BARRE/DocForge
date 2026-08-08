# ====== Code Summary ======
# add per-collection job wall-clock timeout override
#
# Revision: b1c7e9a4d2f8
# Revises: a7b4c9e2f1d3
# Created: 2026-08-08 00:00:00.000000
#
# Adds one nullable column ``job_timeout_seconds`` (Float) to ``collection``. It overrides the
# whole-ingest-job wall-clock budget for that collection; NULL means the collection falls back to the
# worker's global ``WORKER_JOB_TIMEOUT_SECONDS`` default. Mirrors the other nullable limit fields on
# the table (e.g. ``max_file_size_bytes``).
#
# Data safety: STRICTLY ADDITIVE. The column is nullable with a NULL server default, so every
# pre-existing collection row backfills to NULL (global default) without a separate UPDATE pass. No
# existing column is dropped, renamed, or retyped. The downgrade drops the column, discarding any
# per-collection override (a plain, reversible schema-only change).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b1c7e9a4d2f8"
down_revision = "a7b4c9e2f1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable per-collection job-timeout override column (existing rows → NULL)."""
    op.add_column(
        "collection",
        sa.Column("job_timeout_seconds", sa.Float(), nullable=True, server_default=None),
    )


def downgrade() -> None:
    """Drop the per-collection job-timeout override column, reverting to the global-only budget."""
    op.drop_column("collection", "job_timeout_seconds")
