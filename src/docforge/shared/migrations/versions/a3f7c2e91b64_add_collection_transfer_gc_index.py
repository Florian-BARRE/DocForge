# ====== Code Summary ======
# add the garbage-collection index for the expired-export sweep on ``collection_transfer``
#
# Revision: a3f7c2e91b64
# Revises: f2b9d7c4a1e8
# Created: 2026-09-01 00:00:00.000000
#
# Adds one read-path index on ``collection_transfer`` for the ``gc_expired_transfers`` worker cron.
# Every 15 minutes that sweep runs
# ``WHERE kind = 'export' AND s3_key IS NOT NULL AND expires_at IS NOT NULL AND expires_at < now()``
# to find bundles whose expiry has passed, so it can delete the S3 blob and the row. With no index this
# is a full seq-scan of ``collection_transfer`` on every tick. ``ix_collection_transfer_expires_at`` is a
# PARTIAL btree on ``expires_at`` whose predicate pins the three STATIC conjuncts the sweep filters on
# (``kind = 'export' AND s3_key IS NOT NULL AND expires_at IS NOT NULL``); the time bound
# ``expires_at < now()`` is deliberately NOT in the predicate (``now()`` is STABLE, not IMMUTABLE, and
# Postgres rejects a non-immutable partial-index predicate) — it is served as a range scan on the
# indexed ``expires_at`` column at query time. The predicate keeps the index to just the live export
# bundles (imports, in-flight/failed exports with no ``s3_key``, and keep-forever exports with a NULL
# expiry are all excluded), so it stays tiny regardless of how many transfer rows accumulate.
#
# Data safety: STRICTLY ADDITIVE and fully reversible. No table, column, or constraint is created,
# dropped, renamed, or retyped — only one index is added, and the downgrade drops exactly that index.
# ``kind`` is a ``value_enum`` (native_enum=False) stored as VARCHAR, so ``kind = 'export'`` is a plain
# string comparison with no enum cast — Alembic's comparator normalises this partial predicate and
# reconciles it against the model's ``postgresql_where`` (verified via ``alembic check``), so the index
# is also declared on the model's ``__table_args__``. Raw DDL is used because ``op.create_index`` cannot
# cleanly express the partial WHERE predicate. The build takes a SHARE lock that blocks writes to
# ``collection_transfer`` for its duration; this table holds one row per export/import job (tiny), so a
# plain transactional CREATE INDEX is fine.

# ====== Third-Party Library Imports ======
from alembic import op

# Revision identifiers used by Alembic.
revision = "a3f7c2e91b64"
down_revision = "f2b9d7c4a1e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the partial expiry index over the live export bundles the GC sweep scans."""
    # 1. Partial index on expires_at for the expired-export sweep — raw DDL (op.create_index can't
    #    express the partial predicate). now() is intentionally excluded (non-immutable).
    op.execute(
        "CREATE INDEX ix_collection_transfer_expires_at ON collection_transfer (expires_at) "
        "WHERE kind = 'export' AND s3_key IS NOT NULL AND expires_at IS NOT NULL"
    )


def downgrade() -> None:
    """Drop exactly the index added by ``upgrade``."""
    op.execute("DROP INDEX IF EXISTS ix_collection_transfer_expires_at")
