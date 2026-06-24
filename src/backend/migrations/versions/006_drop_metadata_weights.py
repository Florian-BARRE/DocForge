"""Drop metadata_field.weight_lexical and weight_semantic — per-field RRF weights removed.

All searchable fields now use equal weight (1.0) by default; callers override at search
time via weight_overrides instead of storing static weights in the schema.

Revision ID: 006
Revises: 005
Create Date: 2026-06-16
"""

from alembic import op


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("metadata_field", "weight_lexical")
    op.drop_column("metadata_field", "weight_semantic")


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column("metadata_field", sa.Column("weight_lexical", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("metadata_field", sa.Column("weight_semantic", sa.Float(), nullable=False, server_default="1.0"))
