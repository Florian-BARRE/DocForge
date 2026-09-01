# ====== Code Summary ======
# Fixtures for the DB-BACKED suite (`-m db`) — every test here needs a real Postgres. Each test run
# gets its OWN throwaway database (created via an admin connection, dropped on teardown), so the
# shared dev-stack database (postgres:10041/docforge, the one the app/worker actually use) is never
# touched. Two flavours are needed: a full-chain ``alembic_roundtrip_db`` (one per test — it tears
# the schema all the way down to base, so it cannot be shared) and a session-scoped
# ``migrated_db_dsn`` already sitting at head (shared by the drift check + the query-execution
# suite, which only ever INSERT/SELECT — never touch DDL).
#
# Connection details default to the documented dev stack (CLAUDE.md "Ports dev": postgres on host
# 10041, user/db "docforge") and can be overridden via TEST_POSTGRES_* env vars for CI, where the
# service container will live on a different host/port.

# ====== Standard Library Imports ======
import asyncio
import os
import pathlib
import uuid
from collections.abc import Iterator

# ====== Third-Party Library Imports ======
import asyncpg
import pytest
from alembic.config import Config

# tests/db/conftest.py -> parents[2] is the docforge repo root (src/docforge/).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "shared"
ALEMBIC_INI = SHARED_DIR / "alembic.ini"

POSTGRES_HOST = os.environ.get("TEST_POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("TEST_POSTGRES_PORT", "10041"))
POSTGRES_USER = os.environ.get("TEST_POSTGRES_USER", "docforge")
POSTGRES_PASSWORD = os.environ.get("TEST_POSTGRES_PASSWORD", "docforge")
# The maintenance database CREATE/DROP DATABASE run against — never the app's own "docforge" db.
POSTGRES_ADMIN_DB = os.environ.get("TEST_POSTGRES_ADMIN_DB", "postgres")


def asyncpg_dsn(dbname: str) -> str:
    """The raw (no ``+asyncpg`` driver marker) DSN asyncpg's admin connection needs."""
    return (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{dbname}"
    )


def sqlalchemy_dsn(dbname: str) -> str:
    """The SQLAlchemy-style DSN the app/alembic ``POSTGRES_DSN`` env var expects."""
    return (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{dbname}"
    )


async def _create_database(name: str) -> None:
    """CREATE DATABASE over an admin connection (DDL that cannot run inside a transaction)."""
    conn = await asyncpg.connect(asyncpg_dsn(POSTGRES_ADMIN_DB))
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(name: str) -> None:
    """Terminate any lingering backends on the throwaway db, then DROP it."""
    conn = await asyncpg.connect(asyncpg_dsn(POSTGRES_ADMIN_DB))
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await conn.close()


def alembic_config(dbname: str) -> Config:
    """An Alembic ``Config`` wired at the given throwaway db (``POSTGRES_DSN`` env, read by env.py).

    Alembic re-executes ``env.py`` fresh on every command, so mutating the env var right before each
    call (rather than once at import time) keeps the whole round-trip pointed at the SAME database.
    """
    os.environ["POSTGRES_DSN"] = sqlalchemy_dsn(dbname)
    return Config(str(ALEMBIC_INI))


@pytest.fixture
def alembic_roundtrip_db() -> Iterator[str]:
    """A fresh throwaway database, dropped after the test — for a full up/down/up cycle."""
    name = f"docforge_test_roundtrip_{uuid.uuid4().hex[:12]}"
    asyncio.run(_create_database(name))
    try:
        yield name
    finally:
        asyncio.run(_drop_database(name))


@pytest.fixture(scope="session")
def migrated_db_name() -> Iterator[str]:
    """A throwaway database migrated ONCE to head — shared by the drift check + query-execution
    tests (both are DDL-free: index/column comparisons and plain INSERT/SELECT)."""
    name = f"docforge_test_head_{uuid.uuid4().hex[:12]}"
    asyncio.run(_create_database(name))
    from alembic import command  # noqa: PLC0415 — deferred so collection-time imports stay cheap

    command.upgrade(alembic_config(name), "head")
    try:
        yield name
    finally:
        asyncio.run(_drop_database(name))


@pytest.fixture(scope="session")
def migrated_db_dsn(migrated_db_name: str) -> str:
    """The SQLAlchemy DSN of the session-scoped, head-migrated throwaway database."""
    return sqlalchemy_dsn(migrated_db_name)
