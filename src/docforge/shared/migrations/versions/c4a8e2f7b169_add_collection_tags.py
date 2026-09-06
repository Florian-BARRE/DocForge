# ====== Code Summary ======
# add collection.tags (user-facing labels for grouping/filtering collections)
#
# Revision: c4a8e2f7b169
# Revises: b3e8f1a6c204
# Created: 2026-09-06 00:00:00.000000
#
# Adds ``collection.tags`` (VARCHAR[] NOT NULL, server_default empty array): free-form, user-facing
# labels the UI uses to group and filter collections (e.g. "demo", "imported", "custom"). Mirrors the
# existing ``collection.supported_formats`` array column, but carries a constant empty-array default so
# the add is additive. Purely additive.
#
# Data safety: SAFE ONLINE. The column is NOT NULL but declared with a CONSTANT server_default
# (``'{}'::varchar[]``), which on PostgreSQL 11+ is a metadata-only change: the default is recorded in
# the catalog with no table rewrite and no backfill, and every pre-existing collection row reads back as
# an empty tag list. The downgrade drops the column verbatim, restoring the prior column shape exactly;
# it loses only the labels, which are cosmetic UI grouping metadata with no downstream dependency.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision = "c4a8e2f7b169"
down_revision = "b3e8f1a6c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the non-null collection.tags array with a constant empty-array default."""
    op.add_column(
        "collection",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )


def downgrade() -> None:
    """Drop collection.tags, restoring the prior column shape verbatim."""
    op.drop_column("collection", "tags")
