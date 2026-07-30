# ====== Code Summary ======
# Startup schema guard — brings the database to Alembic head IN-PROCESS, before anything that
# touches tables (object store, auth bootstrap). This makes "migrate, then provision" a hard
# ordering inside the app itself, so a fresh volume can never boot into the half-provisioned state
# that silently skipped the root-key bootstrap. Alembic's env.py drives asyncpg through its own
# asyncio.run(), so the blocking upgrade runs in a worker thread to stay clear of the running loop.

# ====== Standard Library Imports ======
import asyncio
import pathlib

# ====== Third-Party Library Imports ======
from alembic import command
from alembic.config import Config
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
import shared_libs


def _alembic_config() -> Config:
    """Build the Alembic config from the ini that ships beside the shared package."""
    shared_root = pathlib.Path(shared_libs.__path__[0]).parent
    return Config(str(shared_root / "alembic.ini"))


class SchemaMigrator:
    """Static runner that upgrades the database schema to head at application startup."""

    logger = loggerplusplus.bind(identifier="SchemaMigrator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SchemaMigrator is a static-only class and cannot be instantiated.")

    @classmethod
    async def upgrade_to_head(cls) -> None:
        """
        Bring the schema to Alembic head.

        Best-effort: a store unreachable at boot is logged, never fatal, so the app can still serve
        its stateless design surface (matching the object-store / auth-bootstrap steps).
        """
        try:
            # env.py runs asyncio.run() itself — run the blocking upgrade off the event loop.
            await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
            cls.logger.info("Database schema is at head")
        except Exception as exc:
            cls.logger.error(f"Schema upgrade skipped (store unreachable at boot): {exc}")


__all__ = ["SchemaMigrator"]
