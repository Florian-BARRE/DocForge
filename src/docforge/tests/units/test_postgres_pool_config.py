"""PostgresClient connection-pool sizing (W1-11).

The async engine is built with an EXPLICIT pool_size/max_overflow/pool_recycle so a scaled deployment
(app + N worker replicas) can be kept under Postgres' max_connections ceiling. These knobs used to be
SQLAlchemy's implicit 5 + 10 default; this guards that they are now wired from config and applied
verbatim to the engine's pool. No connection is opened (asyncpg connects lazily), so this needs no DB.
"""

from shared_libs.services.db.postgresql import PostgresClient

_DSN = "postgresql+asyncpg://user:pass@localhost/db"


def test_engine_pool_is_sized_from_the_configured_values() -> None:
    """The pool reflects the exact pool_size / max_overflow / recycle the client was built with."""
    client = PostgresClient(_DSN, pool_size=7, max_overflow=3, pool_recycle_seconds=1234)
    pool = client._engine.pool

    assert pool.size() == 7
    assert pool._max_overflow == 3
    assert pool._recycle == 1234
    # pre_ping stays ON alongside recycle — the per-checkout SELECT 1 catches a connection dropped
    # within the recycle window; the two are complementary.
    assert pool._pre_ping is True


def test_defaults_match_the_historical_implicit_sizing() -> None:
    """The defaults preserve the pre-existing behaviour (5 + 10 = 15 connections/process)."""
    client = PostgresClient(_DSN)
    pool = client._engine.pool

    assert pool.size() == 5
    assert pool._max_overflow == 10
