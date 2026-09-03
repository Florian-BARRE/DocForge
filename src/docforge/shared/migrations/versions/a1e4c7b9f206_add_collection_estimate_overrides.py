# ====== Code Summary ======
# add per-collection cost-estimate override blob
#
# Revision: a1e4c7b9f206
# Revises: f4c1a9d7e2b3
# Created: 2026-09-03 00:00:00.000000
#
# Adds one nullable JSONB column ``estimate_overrides`` to ``collection``. It holds a PARTIAL override
# of the cost-estimate inputs for that collection; NULL means the collection uses the global defaults
# (the hardcoded RateTable in nodes/openai_compat/pricing.py and the EstimateAssumptions coefficients
# in ingest/estimate/models.py). When set, the value is a partial dict merged over those defaults by
# the estimator, shape:
#   {"rates": {"models": {"gpt-4o-mini": {"input": 0.15, "output": 0.60}}, "embed": {...}, "ocr": {...}},
#    "assumptions": {"tokens_per_page": 500, "images_per_page": 0.5, ...}}
# Mirrors the other lean JSONB blobs on the table (``pipeline`` / ``search``), but nullable so absence
# is distinguishable from an empty override.
#
# Data safety: STRICTLY ADDITIVE. The column is nullable with a NULL server default, so every
# pre-existing collection row backfills to NULL (global defaults) without a separate UPDATE pass. No
# existing column is dropped, renamed, or retyped. The downgrade drops the column, discarding any
# per-collection override (a plain, reversible schema-only change).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision = "a1e4c7b9f206"
down_revision = "f4c1a9d7e2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable per-collection estimate-override column (existing rows -> NULL = defaults)."""
    op.add_column(
        "collection",
        sa.Column(
            "estimate_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=None
        ),
    )


def downgrade() -> None:
    """Drop the per-collection estimate-override column, reverting to the global-only estimate inputs."""
    op.drop_column("collection", "estimate_overrides")
