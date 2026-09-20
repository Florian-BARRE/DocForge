# ====== Code Summary ======
# add column trace_payload_bytes to job (Integer NOT NULL server_default 0)
#
# Revision: c7a3f1e9d2b4
# Revises: a1f4c9e7b2d3
# Created: 2026-09-20 00:00:00.000000
#
# Adds ``job.trace_payload_bytes`` — the total bytes of a job's heavy FULL execution-trace payloads
# stored raw in S3 under ``trace/{job_id}/`` (deduped by content-addressed key). Those objects are
# NOT tracked in the ``blob`` registry, so the storage footprint could not see them; recording the
# summed size on the job row lets the footprint surface (and the trace-payload purge reclaim, by
# zeroing this counter) that space via a plain SQL SUM. It matches the model's
# ``mapped_column(Integer, nullable=False, server_default=text("0"), default=0)`` declaration exactly,
# so ``--autogenerate`` reconciles it rather than proposing to drop it.
#
# DOCUMENTED LIMITATION (deliberate — no backfill): only trace stored AFTER this column ships is
# counted. Payloads written before it existed read as 0 until re-stored (a reingest re-stores them
# and sets the true total). This mirrors the filterable-metadata backfill tradeoff and is acceptable.
#
# Data safety: SAFE + STRICTLY ADDITIVE. Adding a NOT NULL column WITH a server_default backfills
# every existing row to 0 in one metadata-only operation (no table rewrite for a fixed-width Integer
# default on PG 16); no column is dropped, renamed or retyped, and no constraint changes. The
# downgrade drops the column verbatim, restoring the previous shape exactly.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "c7a3f1e9d2b4"
down_revision = "a1f4c9e7b2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the ``trace_payload_bytes`` counter to ``job`` (NOT NULL, server_default 0)."""
    op.add_column(
        "job",
        sa.Column(
            "trace_payload_bytes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """Drop the ``trace_payload_bytes`` column, reverting ``job`` to its previous shape exactly."""
    op.drop_column("job", "trace_payload_bytes")
