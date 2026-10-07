# ====== Code Summary ======
# add column replay_from to job (VARCHAR(32), nullable)
#
# Revision: e5c1a8f3b7d2
# Revises: b4d9e2a7c6f1
# Created: 2026-10-07 00:00:00.000000
#
# Replay-from-stage (D6): an ingest job may re-run only a post-IR stage and its downstream, starting on
# the document's persisted IR (no re-parse). The stage key ("enrich", "chunk", "metagen_chunk",
# "metagen_document", "embed") is stamped on the job row at admission — the worker reads it there (the
# queue carries ids only) and the Activity views show it. NULL = a full pipeline run (every existing row).
#
# Data safety: SAFE ONLINE upgrade (a nullable column, no default, no rewrite). The DOWNGRADE drops the
# column, restoring the previous schema verbatim; only the replay marker of past jobs is lost.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "e5c1a8f3b7d2"
down_revision = "b4d9e2a7c6f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable ``job.replay_from`` stage marker."""
    op.add_column("job", sa.Column("replay_from", sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Drop ``job.replay_from``, restoring the previous ``job`` shape exactly."""
    op.drop_column("job", "replay_from")
