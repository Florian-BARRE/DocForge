"""Drop collection.max_pages — page-count cap removed from the data model.

Revision ID: 005
Revises: 004
Create Date: 2026-06-16
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("collection", "max_pages")


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column("collection", sa.Column("max_pages", sa.Integer(), nullable=True))
