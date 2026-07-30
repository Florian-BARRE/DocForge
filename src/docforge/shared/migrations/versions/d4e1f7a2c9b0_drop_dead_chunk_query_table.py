# ====== Code Summary ======
# drop the dead chunk_query (doc2query) table
#
# Revision: d4e1f7a2c9b0
# Revises: c7f2a9e4b1d8
# Created: 2026-07-30 00:00:00.000000
#
# The chunk_query table backed a doc2query feature (synthetic questions a chunk answers) that was
# never wired: no pipeline node ever produced a question, the IngestionPayload.chunk_queries field
# was always empty, and nothing ever read the table or its companion Qdrant vector
# (content_queries_bm25). Both are removed in the same change; this migration drops the table.
#
# Data safety: the table is ALWAYS EMPTY in every deployment (no producer ever wrote a row), so the
# drop cannot lose data. The downgrade recreates the table's structure exactly (empty), matching the
# initial schema, so a rollback restores the schema shape even though there is nothing to restore.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "d4e1f7a2c9b0"
down_revision = "c7f2a9e4b1d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the always-empty, never-read chunk_query table and its index."""
    op.drop_index(op.f("ix_chunk_query_chunk_id"), table_name="chunk_query")
    op.drop_table("chunk_query")


def downgrade() -> None:
    """Recreate the chunk_query table structure (empty) exactly as the initial schema defined it."""
    op.create_table(
        "chunk_query",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunk.id"],
            name=op.f("fk_chunk_query_chunk_id_chunk"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk_query")),
    )
    op.create_index(op.f("ix_chunk_query_chunk_id"), "chunk_query", ["chunk_id"], unique=False)
