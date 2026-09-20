# ====== Code Summary ======
# widen job.trace_payload_bytes from Integer to BigInteger (NOT NULL, server_default 0 preserved)
#
# Revision: d4b8f2a1c6e7
# Revises: c7a3f1e9d2b4
# Created: 2026-09-20 00:00:01.000000
#
# The counter added by c7a3f1e9d2b4 was ``Integer`` (~2.1 GB cap). A large fan-out job's summed
# trace-payload bytes can exceed that, at which point the best-effort ``set_trace_payload_bytes``
# UPDATE raises ``NumericValueOutOfRange`` — swallowed by the write path's best-effort except, so the
# counter silently stays 0 and the storage footprint under-reports the heaviest traces. Widening to
# ``BigInteger`` (8 bytes, ~9.2 EB) removes the ceiling.
#
# This is a NEW forward migration, deliberately NOT an edit of c7a3f1e9d2b4: the dev DB already ran
# that revision as Integer, so a forward ``alter_column`` is the consistent fix (editing history would
# leave already-migrated databases on the wrong type). It matches the model's
# ``mapped_column(BigInteger, nullable=False, server_default=text("0"), default=0)`` declaration.
#
# Data safety: SAFE, no data loss. ``Integer`` values all fit in ``BigInteger``, so PG 16 widens the
# column in place; the NOT NULL constraint and the ``0`` server_default are re-stated on the alter so
# neither is dropped. The downgrade narrows back to ``Integer`` verbatim — lossless in practice (a row
# whose value already exceeded the Integer cap would overflow on downgrade, but no such row can exist:
# the pre-widen writer could never have persisted one).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "d4b8f2a1c6e7"
down_revision = "c7a3f1e9d2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Widen ``job.trace_payload_bytes`` to BigInteger (NOT NULL, server_default 0 preserved)."""
    op.alter_column(
        "job",
        "trace_payload_bytes",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )


def downgrade() -> None:
    """Narrow ``job.trace_payload_bytes`` back to Integer, restoring the previous shape exactly."""
    op.alter_column(
        "job",
        "trace_payload_bytes",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
