# ====== Code Summary ======
# add chunk.heading_path for clause-level hit provenance
#
# Revision: e5c2b8f4a1d9
# Revises: d4e1f7a2c9b0
# Created: 2026-07-31 00:00:00.000000
#
# Adds the chunk's section ancestry (heading_path) to persistence so a search hit can self-cite the
# section/article it came from (a compliance result naming "Article 7 — Audit rights"). The value is
# computed at chunking time (the heading tree is at hand) and was previously dropped at the IR->DB
# boundary; it is now carried onto the chunk row and lifted onto the hit.
#
# Data safety: STRICTLY ADDITIVE. The column is nullable (a text[] array), so every pre-existing row
# backfills to NULL without a separate UPDATE pass; the read path coalesces NULL to an empty list.
# No existing column is dropped, renamed, or retyped. The downgrade drops the column, discarding the
# stored ancestry (recomputable on re-ingest) — the expected cost of reverting the feature.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# Revision identifiers used by Alembic.
revision = "e5c2b8f4a1d9"
down_revision = "d4e1f7a2c9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the chunk section-ancestry column (NULL on existing rows → empty path on read)."""
    op.add_column(
        "chunk",
        sa.Column("heading_path", ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    """Drop the section-ancestry column, reverting to the pre-provenance schema."""
    op.drop_column("chunk", "heading_path")
