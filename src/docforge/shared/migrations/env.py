# ====== Code Summary ======
# Alembic environment — self-bootstrapping: registers the shared_libs alias (this file lives in
# shared/migrations/, the socle in shared/libs/), imports EVERY table so Base.metadata is
# complete, and reads POSTGRES_DSN from the environment (services/docforge/.env in local
# dev — the same file the apps load; compose injects the value in containers).

# ====== Standard Library Imports ======
import asyncio
import os
import pathlib
import sys
import types

# ====== Third-Party Library Imports ======
from alembic import context
from configplusplus import safe_load_envs
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# ─── Bootstrap the shared_libs alias (mirror of the apps' config helpers) ───
_LIBS = pathlib.Path(__file__).resolve().parent.parent / "libs"
if "shared_libs" not in sys.modules:
    _pkg = types.ModuleType("shared_libs")
    _pkg.__path__ = [str(_LIBS)]
    sys.modules["shared_libs"] = _pkg

# ─── Local dev: load the stack's .env ONLY when the DSN isn't already injected ───
# Containers get POSTGRES_DSN from compose, so this whole block is skipped there — which also
# avoids the host-only ``parents[4]`` path (env.py sits shallower in the container tree).
if "POSTGRES_DSN" not in os.environ:
    safe_load_envs(
        path=pathlib.Path(__file__).resolve().parents[4] / "services" / "docforge",
        verbose=False,
    )

# ====== Internal Project Imports (resolved by the bootstrap above) ======
import shared_libs.services.db.postgresql.tables  # noqa: E402,F401 — fills Base.metadata
from shared_libs.services.db.postgresql.tables.base import Base  # noqa: E402

# The one metadata Alembic diffs against the live schema.
target_metadata = Base.metadata


def _async_database_url() -> str:
    """The asyncpg driver URL used by the live (online) migration path."""
    return os.environ["POSTGRES_DSN"]


def _offline_database_url() -> str:
    """The sync driver URL for offline ``--sql`` mode (asyncpg cannot emit literal SQL)."""
    return _async_database_url().replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection (--sql mode)."""
    context.configure(
        url=_offline_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """Configure Alembic on a sync-facing connection and run the migrations in a transaction.

    Args:
        connection (Connection): The sync-style connection handed over by
            ``AsyncConnection.run_sync`` — asyncpg driven under the hood.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against the live database over asyncpg (the normal mode)."""
    # 1. Build an async engine on the asyncpg DSN.
    engine = create_async_engine(_async_database_url())

    # 2. Bridge to Alembic's sync API via run_sync, then release the engine.
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
