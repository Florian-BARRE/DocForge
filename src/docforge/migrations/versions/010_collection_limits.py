"""Add per-collection resource-admission limits to the collection table (Brique D).

Revision ID: 010
Revises: 009
Create Date: 2026-06-23

Brique D (resource management) introduces an enqueue-time admission gate. Beyond the
deployment-global thresholds carried in RUNTIME_CONFIG, an operator can cap a single
collection's in-flight work and cumulative spend. These caps are stored as dedicated
columns — NOT inside the pipeline JSON blob — so editing a limit never perturbs the
pipeline fingerprint or triggers reindex semantics.

Both columns are additive and nullable, where NULL means "no per-collection cap" (the
collection is governed by the global limits only). Existing rows therefore stay valid
without backfill:
- ``max_in_flight``    NULL = unlimited running+pending jobs for the collection.
- ``budget_cap_usd``   NULL = uncapped cumulative spend for the collection.

No index is added: the admission gate reads these scalar columns by primary key
(collection id) alongside the already-indexed job aggregates.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the two additive per-collection limit columns to ``collection``."""
    # 1. Per-collection caps — both nullable (NULL = unlimited, governed by global limits only)
    op.add_column("collection", sa.Column("max_in_flight", sa.Integer(), nullable=True))
    op.add_column("collection", sa.Column("budget_cap_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop the per-collection limit columns in reverse order of addition."""
    # 1. Reverse the additions
    op.drop_column("collection", "budget_cap_usd")
    op.drop_column("collection", "max_in_flight")
