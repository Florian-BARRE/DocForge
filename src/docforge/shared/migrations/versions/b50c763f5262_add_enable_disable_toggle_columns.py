# ====== Code Summary ======
# add reversible enable/disable columns (P2)
#
# Revision: b50c763f5262
# Revises: 0d66d7d3c37c
# Created: 2026-07-09 00:00:00.000000
#
# Phase 2 of the reversible enable/disable feature. Adds the persistence for a document-level
# on/off toggle and a chunk-level structural role + manual override. No search/API/worker logic
# rides on these columns yet (P3-P5); this revision only puts the schema in place.
#
# A chunk's EFFECTIVE searchable state is resolved downstream as:
#     enabled_override ?? role_default_enabled(role)
# where role_default_enabled lives in shared/libs/public_models/chunk_role.py.
#
# Data safety: STRICTLY ADDITIVE. All three columns are added with server defaults (or NULL for
# the nullable override), so every pre-existing row backfills without a separate UPDATE pass:
#   - document.enabled        -> true   (all existing documents stay searchable)
#   - chunk.role              -> 'body'  (existing chunks classified as substantive content)
#   - chunk.enabled_override  -> NULL    (no manual override; effective state defers to the role)
# No existing column is dropped, renamed, or retyped, so the upgrade cannot lose data. The
# downgrade drops the three columns; that discards any user-entered per-chunk overrides and any
# pipeline-assigned roles, which is the expected cost of reverting the feature and is called out
# here explicitly. `role` is a plain VARCHAR (matching block.block_type) — the ChunkRole StrEnum
# owns the value set on the Python side, so no PG enum type is created or dropped.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b50c763f5262"
down_revision = "0d66d7d3c37c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the document-level toggle and chunk-level role + manual override columns."""
    # 1. Document-level plain on/off toggle — defaults to enabled for every existing document.
    op.add_column(
        "document",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # 2. Chunk structural role — a ChunkRole value; existing chunks backfill to "body".
    op.add_column(
        "chunk",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="body"),
    )
    # 3. Chunk manual override — NULL means "no override, defer to the role default".
    op.add_column(
        "chunk",
        sa.Column("enabled_override", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Drop the enable/disable columns, reverting to the pre-P2 schema."""
    # Reverse order of the upgrade; discards user overrides and assigned roles (see data-safety note).
    op.drop_column("chunk", "enabled_override")
    op.drop_column("chunk", "role")
    op.drop_column("document", "enabled")
