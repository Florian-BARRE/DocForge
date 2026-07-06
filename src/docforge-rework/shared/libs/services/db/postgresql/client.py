# ====== Code Summary ======
# PostgresClient — the low-level async gateway to Postgres. It owns the single SQLAlchemy async
# engine and hands out TRANSACTIONAL sessions; the per-table APIs and the high-level Database façade
# run their statements inside a session from here, so nothing else creates engines or manages
# transactions. The DSN is supplied by the caller (from RUNTIME_CONFIG) — never hardcoded.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class PostgresClient(LoggerClass):
    """Async gateway to Postgres — owns the engine and yields transactional sessions."""

    def __init__(self, dsn: str, echo: bool = False) -> None:
        """
        Args:
            dsn (str): asyncpg DSN, e.g. ``postgresql+asyncpg://user:pass@host/db``.
            echo (bool): Echo every emitted SQL statement (debug only).
        """
        LoggerClass.__init__(self)
        self._engine = create_async_engine(dsn, echo=echo, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self.logger.info(f"PostgresClient connected")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """
        Yield a session wrapped in a transaction — commit on success, roll back on error.

        The façade composes several per-table APIs inside ONE session so their writes commit
        (or roll back) together.

        Yields:
            AsyncSession: The unit of work the APIs run their statements in.
        """
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Close the engine's connection pool — call on shutdown."""
        await self._engine.dispose()
        self.logger.info(f"PostgresClient disposed")


__all__ = ["PostgresClient"]
