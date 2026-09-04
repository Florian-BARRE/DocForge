# ====== Code Summary ======
# FastAPI lifespan — the app's bootstrap and orderly shutdown: banner, runtime configuration
# dump, then the design-surface services sanity log. The design surface is stateless (builder /
# validator are pure), so startup is light; heavier services (database, queues) will add their
# numbered steps here when the worker/persistence wiring lands.

# ====== Standard Library Imports ======
import unicodedata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
from pyfiglet import Figlet

# ====== Internal Project Imports ======
from shared_libs.observability import ConfigDumpHelpers

# ====== Local Project Imports ======
from .context import CONTEXT
from .libs.auth import AuthBootstrap
from .libs.schema import SchemaMigrator

# Total number of startup steps — update when adding/removing steps.
TOTAL_STEPS = 5


def lifespan() -> Any:
    """
    Return the FastAPI lifespan context manager factory.

    Returns:
        Any: Async context manager for FastAPI's lifespan parameter.
    """

    def log_step(step: int, message: str) -> None:
        """Log a numbered startup step."""
        CONTEXT.logger.info(f"\n[{step}/{TOTAL_STEPS}] {message}...")

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[None]:
        _ = app
        try:
            # 1. Print the startup banner (accents stripped for the figlet font).
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c
                    for c in unicodedata.normalize("NFD", CONTEXT.RUNTIME_CONFIG.FASTAPI_APP_NAME)
                    if unicodedata.category(c) != "Mn"
                )
            )
            CONTEXT.logger.info(banner)

            # 2. Log the runtime configuration. configplusplus masks values whose NAME looks like a
            #    secret; ConfigDumpHelpers additionally redacts the ``user:pass@`` userinfo of URL/DSN
            #    values (POSTGRES_DSN / REDIS_URL carry the password in the value under a name the
            #    heuristic misses), so no credential reaches stdout or Loki.
            log_step(1, "Runtime configuration")
            CONTEXT.logger.info(ConfigDumpHelpers.masked(CONTEXT.RUNTIME_CONFIG))

            # 3. The design-surface services (stateless — instantiated in entrypoint.py).
            log_step(2, "Pipeline design surface")
            CONTEXT.logger.info(
                f"Builder/validator ready — palette, mechanics and artefacts are "
                f"served from the node registry"
            )

            # 4. Bring the schema to Alembic head BEFORE anything reads/writes tables — guarantees
            #    the migrate → provision ordering inside the process, so a fresh volume can never
            #    boot into a half-provisioned state. Guarded: only when a database is wired.
            log_step(3, "Database schema")
            if hasattr(CONTEXT, "database"):
                await SchemaMigrator.upgrade_to_head()

            # 5. Provision the blob bucket on a fresh volume (idempotent). Guarded: the design
            #    surface can boot without stores wired, so only run when a database is present.
            log_step(4, "Object store")
            if hasattr(CONTEXT, "database"):
                await CONTEXT.database.ensure_object_store()

            # 6. Provision the root credential when auth is on (idempotent, best-effort). Runs after
            #    the schema step, so the tables it needs are guaranteed present.
            log_step(5, "Authentication bootstrap")
            await AuthBootstrap.ensure_root_credential()

            # 6. Yield — the app is now serving.
            yield

        finally:
            # Shutdown in reverse order. Each teardown is hasattr-guarded because the app can boot
            # with only a subset of services wired (design surface serves without stores/queue).
            CONTEXT.logger.info(f"Shutting down...")
            # 1. Drain the enqueue-only Redis pool.
            if hasattr(CONTEXT, "queue"):
                await CONTEXT.queue.close()
            # 2. Release the store connections (disposes the Postgres engine, closes Qdrant).
            if hasattr(CONTEXT, "database"):
                await CONTEXT.database.close()

    return _lifespan


__all__ = ["lifespan"]
