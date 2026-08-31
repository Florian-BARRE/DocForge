# ====== Code Summary ======
# add performance indexes for the server-side corpus document grid
#
# Revision: c3e9a1f7d2b4
# Revises: b1c7e9a4d2f8
# Created: 2026-08-31 00:00:00.000000
#
# Adds seven read-path indexes backing DocumentQueryApi's filter/sort/count at 100k-document scale.
# On ``document``: four collection-scoped btree composites (leading ``collection_id`` matches the
# always-present scope predicate) for the default created-at ordering plus the status / filename /
# enabled filters. On ``document_metadata``: a field-leading composite ``(field_id, document_id)``
# for the correlated EXISTS + scalar sort subquery, a FUNCTIONAL btree on
# ``(field_id, (value #>> '{}'))`` mirroring the exact expression the query builder
# emits for eq/in/ordered metadata predicates, and a GIN index on the raw JSONB ``value`` for
# list-field containment (``has_any``). The functional and GIN indexes use raw DDL because
# ``op.create_index`` cannot express a functional key or the ``USING gin`` access method cleanly.
#
# Data safety: STRICTLY ADDITIVE and fully reversible. No table, column, or constraint is created,
# dropped, renamed, or retyped — only indexes are added, and the downgrade drops exactly the seven it
# adds. None duplicate an existing index: the single-column ``field_id`` index and the
# ``UNIQUE(document_id, field_id)`` constraint are both left intact (the new composites lead with a
# different column, so neither is redundant). Index builds take a SHARE lock that blocks writes to the
# target table for the build's duration; at ~100k rows this is a sub-second-to-seconds window, so a
# plain (transactional) CREATE INDEX is used. If these tables grow large enough that the write-blocking
# window becomes unacceptable, split this into a non-transactional migration using CREATE INDEX
# CONCURRENTLY inside ``op.get_context().autocommit_block()`` (CONCURRENTLY cannot run inside Alembic's
# wrapping transaction, and leaves an INVALID index behind on failure — hence not the default here).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "c3e9a1f7d2b4"
down_revision = "b1c7e9a4d2f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the grid's read-path indexes (four on ``document``, three on ``document_metadata``)."""
    # 1. document — collection-scoped btree composites for the grid's default sort and base filters.
    op.create_index(
        "ix_document_collection_created_at",
        "document",
        ["collection_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_document_collection_status", "document", ["collection_id", "status"])
    op.create_index("ix_document_collection_filename", "document", ["collection_id", "filename"])
    op.create_index("ix_document_collection_enabled", "document", ["collection_id", "enabled"])

    # 2. document_metadata — field-leading composite for the correlated EXISTS / scalar sort subquery.
    op.create_index("ix_docmeta_field_document", "document_metadata", ["field_id", "document_id"])

    # 3. Functional btree matching the query builder's exact expression for eq/in/ordered predicates.
    # Corrected from a broken 1-arg ``jsonb_extract_path_text(value)`` (no such Postgres function) to
    # the ``value #>> '{}'`` empty-path text extraction the runtime builder now emits inline.
    op.execute(
        "CREATE INDEX ix_docmeta_field_value_text "
        "ON document_metadata (field_id, ((value #>> '{}')))"
    )

    # 4. GIN on the raw JSONB value — backs list-field containment (has_any / @>).
    op.execute("CREATE INDEX ix_docmeta_value_gin ON document_metadata USING gin (value)")


def downgrade() -> None:
    """Drop exactly the seven indexes added by ``upgrade`` (reverse order)."""
    # 1. document_metadata indexes (raw DDL for the expression/GIN ones, symmetric with upgrade).
    op.execute("DROP INDEX IF EXISTS ix_docmeta_value_gin")
    op.execute("DROP INDEX IF EXISTS ix_docmeta_field_value_text")
    op.drop_index("ix_docmeta_field_document", table_name="document_metadata")

    # 2. document indexes.
    op.drop_index("ix_document_collection_enabled", table_name="document")
    op.drop_index("ix_document_collection_filename", table_name="document")
    op.drop_index("ix_document_collection_status", table_name="document")
    op.drop_index("ix_document_collection_created_at", table_name="document")
