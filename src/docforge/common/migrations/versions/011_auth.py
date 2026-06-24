"""Add authentication + GitHub-style per-collection authorization tables.

Revision ID: 011
Revises: 010
Create Date: 2026-06-24

Introduces the data-layer foundation for auth/authz. Three new tables:

- ``app_user``         — authentication identities. Stores an argon2 password hash (never
                         plaintext), a global role (``root`` | ``user``), and an active flag.
- ``api_key``          — user-owned API keys. Only the key HASH is stored (looked up on every
                         request, hence indexed); the plaintext is shown once and never persisted.
                         Soft-revoked via ``revoked_at``.
- ``collection_grant`` — per-collection authorization (GitHub-collaborator model): one role
                         (``read`` | ``write`` | ``admin``) per (user, collection), enforced by a
                         unique constraint. ``granted_by`` records the granter (SET NULL on their
                         deletion so the grant survives).

Data safety:
- This migration is purely additive — it creates new tables and touches no existing data, so
  it carries no backfill and no risk to current rows.
- FK cascade choices: deleting a user removes its api_key + collection_grant rows; deleting a
  collection removes its grants; deleting a *granter* nulls ``granted_by`` rather than deleting
  the grant. ``downgrade()`` drops the three tables (and their indexes/constraints) in reverse
  dependency order — it is destructive of auth data only and is the intended rollback.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the app_user, api_key, and collection_grant tables with their indexes."""
    # 1. app_user — authentication identity (parent of api_key and collection_grant)
    op.create_table(
        "app_user",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Unique login handle — also the lookup index for get_by_username.
    op.create_index("ix_app_user_username", "app_user", ["username"], unique=True)

    # 2. api_key — user-owned keys; lookup by hash on every authenticated request
    op.create_table(
        "api_key",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Owner lookup (list a user's keys) + hash lookup (per-request auth path).
    op.create_index("ix_api_key_user_id", "api_key", ["user_id"])
    op.create_index("ix_api_key_key_hash", "api_key", ["key_hash"])

    # 3. collection_grant — per-collection authorization (one role per user/collection)
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
        # At most one grant per (user, collection) — backs the repository upsert.
        sa.UniqueConstraint(
            "user_id", "collection_id", name="uq_collection_grant_user_collection"
        ),
    )
    # List a collection's collaborators / a user's collections.
    op.create_index(
        "ix_collection_grant_collection_id", "collection_grant", ["collection_id"]
    )
    op.create_index("ix_collection_grant_user_id", "collection_grant", ["user_id"])


def downgrade() -> None:
    """Drop the three auth tables (and their indexes) in reverse dependency order."""
    # 1. collection_grant first (it FKs into app_user and collection)
    op.drop_index("ix_collection_grant_user_id", table_name="collection_grant")
    op.drop_index("ix_collection_grant_collection_id", table_name="collection_grant")
    op.drop_table("collection_grant")

    # 2. api_key next (FKs into app_user)
    op.drop_index("ix_api_key_key_hash", table_name="api_key")
    op.drop_index("ix_api_key_user_id", table_name="api_key")
    op.drop_table("api_key")

    # 3. app_user last (now unreferenced)
    op.drop_index("ix_app_user_username", table_name="app_user")
    op.drop_table("app_user")
