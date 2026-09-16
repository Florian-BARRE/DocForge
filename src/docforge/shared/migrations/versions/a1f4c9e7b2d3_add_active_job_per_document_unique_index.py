# ====== Code Summary ======
# add partial UNIQUE index uq_job_active_per_document on job (document_id) WHERE status IN
# ('pending','running')
#
# Revision: a1f4c9e7b2d3
# Revises: b2d7f9c4e3a1
# Created: 2026-09-16 00:00:00.000000
#
# Adds a PARTIAL UNIQUE index ``uq_job_active_per_document`` on ``job (document_id)`` whose predicate
# covers only the LIVE rows (``status IN ('pending', 'running')``). This makes "at most ONE active job
# per document" a hard DB invariant, race-safe across multiple worker containers — closing the gap
# where a reingest (single or bulk) minted a SECOND job while an older run for the same document was
# still queued/executing, letting their persist phases (Qdrant delete-by-document then upsert of
# reminted chunk ids) interleave and strand orphan points. Because a terminal row
# (``done``/``failed``/``cancelled``) falls OUTSIDE the predicate, finishing a job leaves the active
# set and frees the document for a fresh run. It matches the model's
# ``Index("uq_job_active_per_document", "document_id", unique=True,
# postgresql_where=text("status IN ('pending', 'running')"))`` declaration exactly, so
# ``--autogenerate`` reconciles it rather than proposing to drop it (Alembic normalises the
# ``postgresql_where`` predicate cleanly, as verified for the sibling ``ix_job_status_active``).
#
# Data safety: SAFE + STRICTLY ADDITIVE. Creating an index neither reads nor mutates row data; no
# column is added, dropped, renamed, or retyped, and no other constraint changes. The index is
# UNIQUE over the live rows only — a pre-existing dataset with two live jobs for one document would
# make the CREATE fail; that state is exactly the invariant this forbids and is not produced by the
# current admission paths (which already refuse a second active run). The downgrade drops the index
# verbatim, restoring the previous shape exactly.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "a1f4c9e7b2d3"
down_revision = "b2d7f9c4e3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the partial UNIQUE index enforcing at most one active (pending/running) job per document."""
    op.create_index(
        "uq_job_active_per_document",
        "job",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    """Drop the ``uq_job_active_per_document`` partial UNIQUE index, reverting to no per-document guard."""
    op.drop_index("uq_job_active_per_document", table_name="job")
