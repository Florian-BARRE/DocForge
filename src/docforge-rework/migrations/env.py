# ====== Code Summary ======
# Alembic environment for the docforge-rework schema. It bootstraps the `shared_libs` import alias
# (the tree runs from source, never pip-installed — same trick as the app/worker entrypoints),
# points Alembic at the single Base.metadata that gathers every ORM table, and runs migrations
# asynchronously over asyncpg. The database URL comes from the DATABASE_URL env var — never the ini.

# ====== Standard Library Imports ======
import asyncio
import os
import pathlib
import sys
import types
from logging.config import fileConfig

# ====== Third-Party Library Imports ======
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ─── Register the shared_libs alias so the ORM models import from source ───
_SHARED_LIBS = pathlib.Path(__file__).resolve().parent.parent / "shared" / "libs"
if "shared_libs" not in sys.modules:
    _alias = types.ModuleType("shared_libs")
    _alias.__path__ = [str(_SHARED_LIBS)]
    sys.modules["shared_libs"] = _alias

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import Base  # noqa: E402  (after the alias bootstrap)

# ─── Alembic config + logging ───
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The connection string is injected from the environment, never stored in alembic.ini.
_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    raise RuntimeError(
        "DATABASE_URL is not set — export it (postgresql+asyncpg://user:pass@host/db) "
        "before running alembic."
    )
config.set_main_option("sqlalchemy.url", _database_url)

target_metadata = Base.metadata


def _run_migrations(connection: Connection) -> None:
    """Configure the context on a live connection and run the migrations."""
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    """Open an async engine (asyncpg) and run the migrations over a sync-bridged connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    """Emit SQL without a DB connection (alembic upgrade --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_online())
