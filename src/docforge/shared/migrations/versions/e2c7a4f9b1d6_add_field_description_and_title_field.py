# ====== Code Summary ======
# add metadata_field.description (TEXT NULL) + collection.title_field (VARCHAR(255) NULL)
#
# Revision: e2c7a4f9b1d6
# Revises: b4d1f7a9c2e3
# Created: 2026-10-07 00:00:00.000000
#
# Adds two agent-UX columns. ``metadata_field.description`` is a free-text explanation of what a
# schema field means, surfaced to humans and agents. ``collection.title_field`` names the
# document-scope metadata field whose value is the document's display title; it is a SOFT reference
# to ``metadata_field.field_name`` (same VARCHAR(255) width) with NO foreign key — the API layer
# validates it, so renaming/deleting a field never cascade-breaks the collection row.
#
# Data safety: SAFE ONLINE, purely additive. Both columns are nullable with no default (NULL = "not
# set"), so PG16 adds them as catalog-only changes (no table rewrite, no backfill). The downgrade
# drops both columns verbatim, restoring the prior shapes exactly; it loses only any descriptions /
# title-field choices written since, which nothing at the prior schema reads.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "e2c7a4f9b1d6"
down_revision = "b4d1f7a9c2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable ``metadata_field.description`` and ``collection.title_field`` columns."""
    op.add_column("metadata_field", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("collection", sa.Column("title_field", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Drop both columns, restoring the previous ``collection`` / ``metadata_field`` shapes exactly."""
    op.drop_column("collection", "title_field")
    op.drop_column("metadata_field", "description")
