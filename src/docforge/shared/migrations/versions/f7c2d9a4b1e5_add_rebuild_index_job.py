# ====== Code Summary ======
# add the rebuild_index collection-level job: nullable job.document_id, the 'rebuild_index' kind, the
# one-active-rebuild-per-collection partial unique index, and collection.indexed_embed_signature.
#
# Revision: f7c2d9a4b1e5
# Revises: e2c7a4f9b1d6
# Created: 2026-10-07 00:00:00.000000
#
# A rebuild_index job recreates a collection's Qdrant store from its current schema (no content
# re-embed). It is COLLECTION-scoped, so:
#   - ``job.document_id`` becomes NULLABLE (a rebuild has no document). The FK + CASCADE stay.
#   - ``job.kind`` gains the ``rebuild_index`` value. The column is a VARCHAR(13) (value_enum, no CHECK
#     constraint) and "rebuild_index" is 13 chars, so no DDL is needed for the value itself — only the
#     ``sa.Enum`` rendering in this file documents it.
#   - ``uq_job_active_rebuild_per_collection``: a partial UNIQUE index on ``collection_id`` over the
#     live rebuild rows (kind='rebuild_index' AND status IN pending/running) — the race backstop
#     behind the FOR UPDATE admission (at most one active rebuild per collection).
#   - ``collection.indexed_embed_signature`` (nullable VARCHAR(64)): the embed-space-only part of the
#     indexed baseline, stamped next to ``indexed_signature``. A rebuild copies the CONTENT vectors, so
#     it may only clear ``needs_reindex`` when the embed space is unchanged since the last ingest; this
#     column is how it knows. NULL = unknown (a collection indexed before this column) → a rebuild
#     never clears the flag on it.
#
# Data safety: SAFE ONLINE upgrade (drop NOT NULL, add a nullable column, build a small partial
# index). The DOWNGRADE is LOSSY by necessity: NOT NULL cannot be restored while document-less rows
# exist, so it DELETES every job row whose document_id IS NULL (the rebuild_index jobs and their
# cascaded stage events) before restoring the constraint. It then drops the index and the column,
# restoring the previous shape verbatim.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "f7c2d9a4b1e5"
down_revision = "e2c7a4f9b1d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow document-less jobs, add the active-rebuild index and the embed-signature baseline."""
    # 1. A collection-level job has no document.
    op.alter_column("job", "document_id", existing_type=sa.Uuid(), nullable=True)
    # 2. At most one live rebuild per collection (the admission race backstop).
    op.create_index(
        "uq_job_active_rebuild_per_collection",
        "job",
        ["collection_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'rebuild_index' AND status IN ('pending', 'running')"),
    )
    # 3. The embed-space-only part of the indexed baseline.
    op.add_column(
        "collection",
        sa.Column("indexed_embed_signature", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Drop the column + index; DELETE document-less jobs, then restore ``document_id`` NOT NULL."""
    op.drop_column("collection", "indexed_embed_signature")
    op.drop_index("uq_job_active_rebuild_per_collection", table_name="job")
    # LOSSY: the prior schema cannot hold a document-less job — the rebuild rows are deleted.
    op.execute("DELETE FROM job WHERE document_id IS NULL")
    op.alter_column("job", "document_id", existing_type=sa.Uuid(), nullable=False)
