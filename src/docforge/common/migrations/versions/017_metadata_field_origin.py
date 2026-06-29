"""Add metadata_field.origin to distinguish system / user / LLM-generated fields.

Revision ID: 017
Revises: 016
Create Date: 2026-06-28

S5b introduces a third class of metadata field: LLM-*generated* fields. A field is now one of:
- ``system``    → implicit fields the pipeline always extracts (filename, language, page, …).
- ``user``      → fields the caller authored and whose values are uploaded with each document.
- ``generated`` → fields the caller authored but whose values are produced at ingestion by S5b
                  (referenced by ``pipeline.metagen.targets[*].field``).

The existing boolean ``is_system`` only splits system vs non-system, which cannot express the
user/generated distinction. We add an explicit ``origin`` discriminator and KEEP ``is_system`` as-is
for backward compatibility (existing reads/serializers still rely on it; backend threads ``origin``
through in a follow-up without breaking older callers).

- ADD ``metadata_field.origin`` (VARCHAR(20), NOT NULL, DEFAULT ``'user'``). 'user' is the safe
  default: any pre-existing non-system row is a user-authored field.
- BACKFILL ``origin = 'system'`` WHERE ``is_system = true`` so existing system rows keep their
  identity. (Generated fields did not exist before this migration, so none are backfilled.)

Data safety:
- The ADD is purely additive and backward-compatible: NOT NULL is safe because of the
  ``DEFAULT 'user'`` server default — every existing row is filled in place; the subsequent UPDATE
  only re-labels the system rows.
- ``is_system`` is intentionally NOT removed (no data loss, no break for code still reading it).
- Fully reversible: ``downgrade()`` drops the ``origin`` column. The system/user/generated
  distinction is then represented again only by ``is_system`` (the generated vs user nuance is lost
  on downgrade, which is expected — the feature that produced it is gone).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers — used by Alembic to order migrations.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the origin discriminator column and backfill system rows."""
    # 1. Add origin with a 'user' server default — safe NOT NULL fill for every existing row
    op.add_column(
        "metadata_field",
        sa.Column(
            "origin",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )

    # 2. Re-label existing system fields so their identity survives the new discriminator
    op.execute("UPDATE metadata_field SET origin = 'system' WHERE is_system = true")


def downgrade() -> None:
    """Drop the origin column (keeps is_system as the only field-class signal)."""
    # 1. Drop origin — system/user is again expressed solely by is_system (generated nuance is lost)
    op.drop_column("metadata_field", "origin")
