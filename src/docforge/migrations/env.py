# ====== Code Summary ======
# Alembic migration environment.
# Reads RUNTIME_CONFIG to build the database URL at migration time.
# Supports both offline (SQL script) and online (async + asyncpg) migration modes.

# ====== Standard Library Imports ======
import asyncio
from logging.config import fileConfig

# ====== Third-Party Library Imports ======
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ====== Internal Project Imports ======
# RUNTIME_CONFIG must be imported first — it registers sys.path for internal modules.
from config import RUNTIME_CONFIG
from storage.postgres.models import Base

# Alembic Config object — provides access to the .ini file values.
config = context.config

# Set up Python logging from the alembic.ini file config section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Provide SQLAlchemy metadata to Alembic for autogenerate support.
target_metadata = Base.metadata


def _get_url() -> str:
    """
    Build the asyncpg connection URL from RUNTIME_CONFIG.

    Returns:
        str: postgresql+asyncpg:// DSN.
    """
    return (
        f"postgresql+asyncpg://"
        f"{RUNTIME_CONFIG.POSTGRES_USER}:{RUNTIME_CONFIG.POSTGRES_PASSWORD}"
        f"@{RUNTIME_CONFIG.POSTGRES_HOST}:{RUNTIME_CONFIG.POSTGRES_PORT}"
        f"/{RUNTIME_CONFIG.POSTGRES_DB}"
    )


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode (generates SQL script, no live DB connection).

    Used for audit/review workflows: produces a .sql file instead of applying migrations.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """
    Execute all pending migrations against the given live connection.

    Args:
        connection: An active synchronous-style SQLAlchemy connection (from async engine).
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in online mode using the asyncpg engine.

    Creates a transient async engine, obtains a sync connection via run_sync,
    and runs all pending migrations.
    """
    # 1. Create transient engine for migration only (not reused at runtime)
    engine = create_async_engine(_get_url(), echo=False)

    # 2. Run migrations via sync tunnel (Alembic is not async-native)
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)

    # 3. Dispose the transient engine
    await engine.dispose()


def run_migrations_online() -> None:
    """
    Entry point for online migrations: runs the async migration coroutine.
    """
    asyncio.run(run_async_migrations())


# ─── Entry point — called by Alembic CLI ───────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
