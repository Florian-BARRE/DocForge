"""Drop collection.allowed_providers — dead write-only column removed from the data model.

Revision ID: 012
Revises: 011
Create Date: 2026-06-25

The ``allowed_providers`` column (defined in 001_initial_schema as a NOT NULL ``ARRAY(String)``
with a ``'{}'`` server default) was write-only-with-default: it was always persisted as the empty
array and never read to gate provider selection anywhere in the codebase. An audit confirmed it is
dead, and it has just been removed from ``CollectionModel`` and ``collection_repo``. This migration
brings the schema in line with the model.

Data safety:
- The dropped data is the per-collection provider allow-list. In practice every row holds the empty
  array (the only value ever written), so dropping it loses no meaningful information. The drop is
  still logically destructive: any non-default values that somehow exist would not be recoverable.
- No index exists on the column, so no index needs dropping.
- ``downgrade()`` re-adds the column with the EXACT original definition from 001
  (``postgresql.ARRAY(String)``, ``nullable=False``, ``server_default="{}"``). The NOT NULL +
  server default make the re-add safe on a populated table: existing rows backfill to ``'{}'``.
  The original (always-empty) contents are not restored — only the column shape is reversible.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers — used by Alembic to order migrations.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the dead allowed_providers column from the collection table."""
    op.drop_column("collection", "allowed_providers")


def downgrade() -> None:
    """Re-add allowed_providers with its original 001 definition (NOT NULL ARRAY, default '{}')."""
    op.add_column(
        "collection",
        sa.Column(
            "allowed_providers",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
