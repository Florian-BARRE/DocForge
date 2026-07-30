# ====== Code Summary ======
# add api_key expiry + last-used columns
#
# Revision: c7f2a9e4b1d8
# Revises: b50c763f5262
# Created: 2026-07-29 00:00:00.000000
#
# Adds two optional timestamp columns to the api_key table:
#   - expires_at    -> an optional hard expiry; NULL means the key never expires.
#   - last_used_at  -> the last successful authentication (a throttled best-effort write);
#                      NULL means the key has never been used.
#
# Data safety: STRICTLY ADDITIVE. Both columns are nullable timestamptz with no server default and
# no backfill pass — every pre-existing row gets NULL, which is exactly the correct "never expires /
# never used" semantics. No existing column is dropped, renamed, or retyped, so the upgrade cannot
# lose data and is zero-downtime safe. The downgrade drops both columns; that discards any recorded
# expiry dates and last-used timestamps, which is the expected cost of reverting and is called out
# here explicitly.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "c7f2a9e4b1d8"
down_revision = "b50c763f5262"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the optional expiry and last-used timestamp columns to api_key."""
    # 1. Optional hard expiry — NULL means the key never expires.
    op.add_column(
        "api_key",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 2. Last successful authentication (throttled best-effort write) — NULL means never used.
    op.add_column(
        "api_key",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the expiry and last-used columns, reverting to the pre-expiry schema."""
    # Reverse order of the upgrade; discards recorded expiry dates and last-used timestamps.
    op.drop_column("api_key", "last_used_at")
    op.drop_column("api_key", "expires_at")
