"""Pivot to keys-only authz: add api_key.permissions, drop collection_grant.

Revision ID: 015
Revises: 014
Create Date: 2026-06-26

The multi-user / collaborators authorization model is replaced by a single root account that mints
permissioned API keys. Per-collection authorization now rides on each API key as a JSONB capability
scope instead of living in a separate grants table. Two schema changes:

- ADD ``api_key.permissions`` (JSONB, nullable). Holds the per-collection capability scope:
    {"entries": [{"collection_id": "*"|"<uuid>", "role": "read"|"write"|"admin"|"custom",
                  "capabilities": ["documents.read", ...]}]}
  NULL = FULL access (the static root env key, or any legacy key created before scoping existed) —
  kept full for backward compatibility, so no backfill is needed on existing rows.
- DROP the ``collection_grant`` table (and its indexes/unique constraint), introduced in 011_auth.
  The GitHub-collaborator grant model is gone; permissions now live on keys.

Data safety:
- The ADD is purely additive and backward-compatible (existing keys default to NULL = full access).
- The DROP is DESTRUCTIVE of authorization data: any per-(user, collection) grants are lost and
  cannot be recovered from the schema afterwards. This is intentional — the collaborators feature
  that produced those rows no longer exists.
- ``app_user`` and ``api_key`` are KEPT (root still lives in app_user; keys still FK to it).
- ``downgrade()`` drops ``api_key.permissions`` and re-creates ``collection_grant`` with its EXACT
  011 shape (table + two indexes + the unique (user_id, collection_id) constraint). The re-create
  restores the SHAPE only — the original grant rows are not recoverable.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers — used by Alembic to order migrations.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the api_key.permissions scope column and drop the collection_grant table."""
    # 1. Per-collection capability scope on the key (NULL = full access, back-compat)
    op.add_column(
        "api_key",
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 2. Drop the now-removed grants table (indexes go with it)
    op.drop_index("ix_collection_grant_user_id", table_name="collection_grant")
    op.drop_index("ix_collection_grant_collection_id", table_name="collection_grant")
    op.drop_table("collection_grant")


def downgrade() -> None:
    """Re-create collection_grant (011 shape) and drop the api_key.permissions column."""
    # 1. Re-create collection_grant with its EXACT original 011 definition
    op.create_table(
        "collection_grant",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.UUID(),
            sa.ForeignKey("collection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "granted_by",
            sa.UUID(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "collection_id", name="uq_collection_grant_user_collection"
        ),
    )
    op.create_index(
        "ix_collection_grant_collection_id", "collection_grant", ["collection_id"]
    )
    op.create_index("ix_collection_grant_user_id", "collection_grant", ["user_id"])

    # 2. Drop the permissions scope column
    op.drop_column("api_key", "permissions")
