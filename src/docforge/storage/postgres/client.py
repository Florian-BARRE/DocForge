# ====== Code Summary ======
# PostgreSQL async session factory (SQLAlchemy 2.0 + asyncpg).
# Provides the engine and session-maker used throughout the backend and pipeline.

# ====== Standard Library Imports ======
from contextlib import asynccontextmanager
from typing import AsyncIterator

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ====== Local Project Imports ======
from .models import Base


class PostgresClient(LoggerClass):
    """
    Manages the async SQLAlchemy engine and session factory for DocForge.

    Lifecycle:
        1. ``connect()`` — creates the engine; call once at startup in lifespan.
        2. ``session()`` — async context manager yielding an ``AsyncSession``.
        3. ``close()`` — disposes the engine; call at shutdown.
    """

    def __init__(self, url: str, pool_size: int = 10, echo: bool = False) -> None:
        """
        Initialize with a connection URL and pool settings.

        Args:
            url (str): asyncpg DSN, e.g. ``postgresql+asyncpg://user:pass@host/db``.
            pool_size (int): SQLAlchemy pool size.
            echo (bool): Log all SQL statements (debug only).
        """
        LoggerClass.__init__(self)
        self._url = url
        self._pool_size = pool_size
        self._echo = echo
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        """
        Create the async engine and session factory.

        Raises:
            RuntimeError: If already connected.
        """
        # 1. Guard against double-initialization
        if self._engine is not None:
            raise RuntimeError(f"PostgresClient is already connected.")

        # 2. Create the async engine (asyncpg driver)
        self._engine = create_async_engine(
            self._url,
            pool_size=self._pool_size,
            max_overflow=5,
            echo=self._echo,
            future=True,
        )

        # 3. Create the session factory
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        self.logger.info(f"PostgresClient connected (pool_size={self._pool_size})")

    async def create_tables(self) -> None:
        """
        Create all tables defined in Base metadata (dev / test only).

        In production use Alembic migrations instead.
        """
        if self._engine is None:
            raise RuntimeError(f"PostgresClient is not connected.")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.logger.info(f"All tables created via SQLAlchemy metadata.")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """
        Async context manager that yields a transactional AsyncSession.

        Usage::
            async with postgres_client.session() as session:
                result = await session.execute(select(DocumentModel))

        Yields:
            AsyncSession: An open, transaction-scoped session.

        Raises:
            RuntimeError: If the client is not yet connected.
        """
        # 1. Guard
        if self._session_factory is None:
            raise RuntimeError(f"PostgresClient is not connected.")

        # 2. Yield session with automatic commit / rollback
        async with self._session_factory() as session:
            async with session.begin():
                yield session

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self.logger.info(f"PostgresClient disconnected.")

    @staticmethod
    def build_url(
        user: str, password: str, host: str, port: int, db: str
    ) -> str:
        """
        Build an asyncpg DSN from individual connection parameters.

        Args:
            user (str): Database user.
            password (str): Database password.
            host (str): Database host.
            port (int): Database port.
            db (str): Database name.

        Returns:
            str: A ``postgresql+asyncpg://`` connection string.
        """
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
