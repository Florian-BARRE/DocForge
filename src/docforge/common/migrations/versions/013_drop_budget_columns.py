"""Drop the dead budget columns — the budget concept was removed from the data model.

Revision ID: 013
Revises: 012
Create Date: 2026-06-25

The whole budget concept (per-collection spend cap + per-job cumulative spend) has been removed
from the codebase: the models no longer carry these columns and every repo/route/test that read or
wrote them is gone (unit suite green). This migration brings the schema in line with the model by
dropping the two now-orphaned columns:

- ``collection.budget_cap_usd``  — added in 010_collection_limits as a nullable ``Float`` (Brique D
  per-collection cumulative-spend cap; NULL = uncapped). Dropped here.
- ``job.budget_spent``           — defined in 001_initial_schema as a NOT NULL ``Float`` with a
  ``'0.0'`` server default (per-job cumulative spend accumulator). Dropped here.

Data safety:
- This drop is logically DESTRUCTIVE: any spend caps and accumulated per-job spend values are lost
  and cannot be recovered from the schema after the drop. This is intentional — the feature that
  produced these numbers no longer exists, so the data is dead.
- ``collection.max_in_flight`` (the other Brique D limit column from 010) is deliberately KEPT — it
  is still used by the resource-admission gate. Only the budget half is removed.
- Neither column is indexed, so no index needs dropping.
- ``downgrade()`` re-adds both columns with their EXACT original definitions:
    * ``collection.budget_cap_usd`` — ``sa.Float()``, ``nullable=True`` (matches 010).
    * ``job.budget_spent``          — ``sa.Float()``, ``nullable=False``, ``server_default="0.0"``
      (matches 001). The NOT NULL + server default make the re-add safe on a populated ``job``
      table: existing rows backfill to ``0.0``.
  The re-add restores the column SHAPE only — the original values are not recoverable.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the dead budget columns from the collection and job tables."""
    # 1. Per-collection spend cap (added in 010) — no longer modeled
    op.drop_column("collection", "budget_cap_usd")

    # 2. Per-job cumulative spend accumulator (defined in 001) — no longer modeled
    op.drop_column("job", "budget_spent")


def downgrade() -> None:
    """Re-add both budget columns with their EXACT original definitions (001 / 010)."""
    # 1. job.budget_spent — original 001 shape: NOT NULL Float, server default '0.0'
    op.add_column(
        "job",
        sa.Column(
            "budget_spent",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )

    # 2. collection.budget_cap_usd — original 010 shape: nullable Float
    op.add_column(
        "collection",
        sa.Column(
            "budget_cap_usd",
            sa.Float(),
            nullable=True,
        ),
    )
