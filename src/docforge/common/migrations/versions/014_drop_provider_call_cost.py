"""Drop provider_call.cost — the last budget sentinel, removed from the data model.

Revision ID: 014
Revises: 013
Create Date: 2026-06-25

The budget concept has been fully removed from DocForge (see 012/013). ``provider_call.cost`` was
the last remaining column tied to it: a per-provider-call cost accumulator that fed the now-deleted
budget gate. It has just been removed from ``ProviderCallModel`` and from every code path that read
or wrote it (unit suite green at 606 tests). This migration brings the schema in line with the model
by dropping that final orphaned column.

- ``provider_call.cost`` — defined in 001_initial_schema as a NOT NULL ``Float`` with a ``'0.0'``
  server default (per-call cost accumulator for the budget gate). Dropped here.

Data safety:
- This drop is logically DESTRUCTIVE: any per-call cost values are lost and cannot be recovered from
  the schema after the drop. This is intentional — the budget feature that produced these numbers no
  longer exists, so the data is dead.
- No index exists on the column, so no index needs dropping.
- ``downgrade()`` re-adds the column with its EXACT original 001 definition: ``sa.Float()``,
  ``nullable=False``, ``server_default="0.0"``. The NOT NULL + server default make the re-add safe on
  a populated ``provider_call`` table: existing rows backfill to ``0.0``. The re-add restores the
  column SHAPE only — the original values are not recoverable.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the dead cost column from the provider_call table."""
    # 1. Per-call cost accumulator (defined in 001) — no longer modeled
    op.drop_column("provider_call", "cost")


def downgrade() -> None:
    """Re-add provider_call.cost with its EXACT original 001 definition (NOT NULL Float, default '0.0')."""
    # 1. provider_call.cost — original 001 shape: NOT NULL Float, server default '0.0'
    op.add_column(
        "provider_call",
        sa.Column(
            "cost",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )
