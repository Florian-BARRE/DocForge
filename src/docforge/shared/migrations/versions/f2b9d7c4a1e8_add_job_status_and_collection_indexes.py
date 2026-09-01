# ====== Code Summary ======
# add hot-path indexes for the stuck-job reaper, active-job scans, and the jobs-by-collection listing
#
# Revision: f2b9d7c4a1e8
# Revises: e8d3c6b1a9f2
# Created: 2026-09-01 00:00:00.000000
#
# Adds two read-path indexes on ``job``. (1) A PARTIAL btree on ``status`` whose predicate covers only
# the ACTIVE set ``status IN ('pending', 'running')`` — the reaper, ``list_active`` and ``queue_depth``
# scan for the handful of live rows on every cron tick, and at 100k+ jobs (all terminal) an unindexed
# ``status`` column forces a full seq-scan. The partial predicate keeps the index tiny (only the live
# rows) and is exactly what those queries hit. (2) A composite ``(collection_id, created_at DESC)`` for
# the jobs-by-collection listing (``WHERE collection_id = X ORDER BY created_at DESC``), which currently
# uses only the single-column ``collection_id`` index and then re-sorts.
#
# Data safety: STRICTLY ADDITIVE and fully reversible. No table, column, or constraint is created,
# dropped, renamed, or retyped — only indexes are added, and the downgrade drops exactly the two it adds.
# Neither duplicates an existing index: the pre-existing single-column ``collection_id`` index is LEFT
# INTACT (the composite supersedes it only for the sorted listing; dropping it is deliberately out of
# scope here). The partial index uses raw DDL because ``op.create_index`` cannot cleanly express a
# partial WHERE predicate; the composite mirrors the grid-index migration's raw ``created_at DESC``
# style via ``sa.text``. Index builds take a SHARE lock that blocks writes to ``job`` for the build's
# duration; at ~100k rows this is a sub-second-to-seconds window, so a plain (transactional)
# CREATE INDEX is used. If ``job`` grows large enough that the write-blocking window becomes
# unacceptable, split this into a non-transactional migration using CREATE INDEX CONCURRENTLY inside
# ``op.get_context().autocommit_block()``.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "f2b9d7c4a1e8"
down_revision = "e8d3c6b1a9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the partial active-status index and the collection-scoped created-at composite on ``job``."""
    # 1. Partial index over the ACTIVE job set only — raw DDL (op.create_index can't express the predicate).
    op.execute(
        "CREATE INDEX ix_job_status_active ON job (status) WHERE status IN ('pending', 'running')"
    )

    # 2. Collection-scoped, created-at-descending composite for the jobs-by-collection listing.
    op.create_index(
        "ix_job_collection_created_at",
        "job",
        ["collection_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    """Drop exactly the two indexes added by ``upgrade`` (reverse order)."""
    op.drop_index("ix_job_collection_created_at", table_name="job")
    op.execute("DROP INDEX IF EXISTS ix_job_status_active")
