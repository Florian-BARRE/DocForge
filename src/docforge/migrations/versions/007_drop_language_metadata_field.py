"""Remove language from the system metadata field catalog.

language is stored on document.language (inferred by S1) and is directly accessible
via the document API — no need to duplicate it as an indexed metadata field.

Revision ID: 007
Revises: 006
Create Date: 2026-06-16
"""

from alembic import op


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM metadata_field WHERE field_name = 'language' AND is_system = TRUE")


def downgrade() -> None:
    # Re-insert the language system field for every existing collection.
    op.execute("""
        INSERT INTO metadata_field (collection_id, field_name, field_type, required, filterable,
                                    lexical, semantic, enum_values, is_system)
        SELECT id, 'language', 'string', FALSE, TRUE, FALSE, FALSE, NULL, TRUE
        FROM collection
        ON CONFLICT DO NOTHING
    """)
