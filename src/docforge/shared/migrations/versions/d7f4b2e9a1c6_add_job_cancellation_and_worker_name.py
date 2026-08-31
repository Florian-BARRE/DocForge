# ====== Code Summary ======
# add job cancellation signal + widen job.status + worker display name
#
# Revision: d7f4b2e9a1c6
# Revises: c3e9a1f7d2b4
# Created: 2026-08-31 00:00:00.000000
#
# Phase-2 job/worker schema changes, all additive except one safe in-place widen:
#   (1) Widen ``job.status`` from VARCHAR(7) to VARCHAR(9). The JobStatus enum gained the terminal
#       value "cancelled" (9 chars), which overflows the old width (the longest prior value was
#       "pending"/"running" = 7). value_enum uses Enum(native_enum=False), whose VARCHAR length is
#       derived from the longest member value, so the ORM now emits VARCHAR(9); this widen matches it
#       exactly (env.py runs with compare_type=True — an off-by-one width would show as drift).
#   (2) Add ``job.cancel_requested`` (BOOLEAN NOT NULL DEFAULT false): the cooperative-stop signal.
#   (3) Add ``worker_heartbeats.worker_name`` (VARCHAR(128) NULL): friendly display label.
#
# Data safety: SAFE ONLINE.
#   - The status widen GROWS a VARCHAR, so no existing value can be truncated (varchar grow is a
#     metadata-only change on PostgreSQL, no table rewrite, no lock beyond a brief ACCESS EXCLUSIVE).
#   - value_enum(native_enum=False) adds NO CHECK constraint, so widening needs no constraint edit.
#   - cancel_requested is NOT NULL with a server_default, so pre-existing rows backfill to false. On
#     PG16 this uses the fast-default optimisation (no full-table rewrite).
#   - worker_name is nullable, so pre-existing heartbeat rows backfill to NULL (the read falls back to
#     worker_id).
#   The downgrade is LOSSY in one direction only: narrowing status back to VARCHAR(7) would raise
#   "value too long" on any "cancelled" row, so the downgrade first remaps cancelled -> failed
#   (the old schema has no cancelled concept). That remap is irreversible — see downgrade().

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "d7f4b2e9a1c6"
down_revision = "c3e9a1f7d2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Widen job.status, add job.cancel_requested, add worker_heartbeats.worker_name."""
    # 1. Widen job.status VARCHAR(7) -> VARCHAR(9) to fit the new "cancelled" value (varchar grow:
    #    metadata-only, no rewrite, no truncation risk).
    op.alter_column(
        "job",
        "status",
        type_=sa.String(length=9),
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )

    # 2. Cooperative-cancel signal on job (NOT NULL, backfills to false via the server_default).
    op.add_column(
        "job",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 3. Friendly worker display name (nullable; pre-existing rows fall back to worker_id at read).
    op.add_column(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    """Reverse the Phase-2 job/worker columns and narrow job.status back to VARCHAR(7)."""
    # 1. Drop the additive columns first (both are pure additions, no dependents).
    op.drop_column("worker_heartbeats", "worker_name")
    op.drop_column("job", "cancel_requested")

    # 2. IRREVERSIBLE remap: the pre-widen schema has no "cancelled" state and its VARCHAR(7) column
    #    would reject the 9-char value ("value too long"). Collapse cancelled jobs to the closest old
    #    terminal state (failed) so the narrow can proceed. This loses the cancelled/failed
    #    distinction for those rows — acceptable only on a deliberate schema rollback.
    op.execute("UPDATE job SET status = 'failed' WHERE status = 'cancelled'")

    # 3. Narrow job.status back to its original width now that no value exceeds 7 chars.
    op.alter_column(
        "job",
        "status",
        type_=sa.String(length=7),
        existing_type=sa.String(length=9),
        existing_nullable=False,
    )
