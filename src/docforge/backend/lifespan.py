# ====== Code Summary ======
# FastAPI lifespan context manager: bootstraps all services at startup and shuts them down
# cleanly in reverse order.  All runtime state is injected into CONTEXT before yielding.

# ====== Standard Library Imports ======
import unicodedata
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

# ====== Third-Party Library Imports ======
from arq import create_pool
from arq.connections import RedisSettings
from pyfiglet import Figlet

# ====== Local Project Imports ======
from .context import CONTEXT

# Total startup steps — update this constant when adding or removing steps.
TOTAL_STEPS = 8


def lifespan() -> Any:
    """
    Return the FastAPI lifespan context manager factory.

    Returns:
        Any: Async context manager for FastAPI's ``lifespan`` parameter.
    """

    def log_step(step: int, message: str) -> None:
        """Log a numbered startup step."""
        CONTEXT.logger.info(f"\n[{step}/{TOTAL_STEPS}] {message}…")

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[None]:
        _ = app
        try:
            # ── Startup ──────────────────────────────────────────────────────

            # 1. Print startup banner with ASCII art
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c
                    for c in unicodedata.normalize(
                        "NFD", CONTEXT.RUNTIME_CONFIG.FASTAPI_APP_NAME
                    )
                    if unicodedata.category(c) != "Mn"
                )
            )
            CONTEXT.logger.info(f"{banner}")

            # 2. Log runtime configuration (secrets masked automatically by configplusplus)
            log_step(1, "Runtime configuration")
            CONTEXT.logger.info(f"{CONTEXT.RUNTIME_CONFIG}")

            # 3. Detect GPU / device availability
            log_step(2, "Device detection (GPU/CPU)")
            CONTEXT.device_manager.detect()

            # 4. Connect to PostgreSQL
            log_step(3, "PostgreSQL connection")
            await CONTEXT.postgres.connect()

            # 5. Connect to SeaweedFS (S3-compatible object store)
            log_step(4, "SeaweedFS S3 connection")
            await CONTEXT.s3.connect()

            # 6. Verify Gotenberg is reachable
            log_step(5, "Gotenberg health check")
            gotenberg_ok = await CONTEXT.converter.health_check()
            if not gotenberg_ok:
                CONTEXT.logger.warning(
                    f"Gotenberg is not reachable at "
                    f"{CONTEXT.RUNTIME_CONFIG.GOTENBERG_URL}. "
                    f"Office format conversion will fail until it is available."
                )
            else:
                CONTEXT.logger.info(f"Gotenberg is healthy.")

            # 7. Connect to Redis arq pool (for job enqueueing from API)
            log_step(6, "Redis arq pool")
            CONTEXT.arq_pool = await create_pool(
                RedisSettings.from_dsn(CONTEXT.RUNTIME_CONFIG.REDIS_URL)
            )
            CONTEXT.logger.info(f"arq Redis pool connected → {CONTEXT.RUNTIME_CONFIG.REDIS_URL}")

            # 8. Connect to Qdrant — always attempted; falls back gracefully if unreachable.
            # If the connection fails, S6/retrieval/metadata_indexer are nulled out so the
            # rest of the pipeline continues without vector indexing.
            log_step(7, "Qdrant vector store")
            if CONTEXT.qdrant is not None:
                try:
                    await CONTEXT.qdrant.connect()
                    CONTEXT.logger.info(
                        f"Qdrant connected → "
                        f"{CONTEXT.RUNTIME_CONFIG.QDRANT_HOST}:{CONTEXT.RUNTIME_CONFIG.QDRANT_PORT}"
                    )
                except Exception as exc:
                    CONTEXT.logger.warning(
                        f"Qdrant not reachable ({exc}). "
                        f"S6 embedding/indexing and hybrid search will be unavailable."
                    )
                    CONTEXT.qdrant = None
                    CONTEXT.retrieval = None
                    CONTEXT.metadata_indexer = None

            # 9. Final startup confirmation
            log_step(8, "Application ready")
            CONTEXT.logger.info(f"DocForge is ready — serving {CONTEXT.RUNTIME_CONFIG.FASTAPI_APP_NAME} v{CONTEXT.RUNTIME_CONFIG.APP_VERSION}")

            # ── Yield — app is now running ────────────────────────────────────
            yield

        finally:
            # ── Shutdown (reverse order, hasattr guards for partial startup) ──
            CONTEXT.logger.info(f"Shutting down DocForge…")

            if hasattr(CONTEXT, "arq_pool"):
                await CONTEXT.arq_pool.close(close_connection_pool=True)

            if hasattr(CONTEXT, "qdrant") and CONTEXT.qdrant is not None:
                await CONTEXT.qdrant.close()

            if hasattr(CONTEXT, "s3"):
                await CONTEXT.s3.close()

            if hasattr(CONTEXT, "postgres"):
                await CONTEXT.postgres.close()

    return _lifespan
