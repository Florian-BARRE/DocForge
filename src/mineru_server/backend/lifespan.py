# ====== Code Summary ======
# Provides the FastAPI lifespan context manager: logs the banner + config and validates config
# fail-fast at startup. Unlike paddle_server, NO model is built at startup — MinerU's VLM model is
# heavy (GPU-only) and this parser is an off-by-default escalation head, so the model loads LAZILY on
# the first /parse request (inside the engine). Uses a hasattr guard in the finally block so a partial
# startup never raises during teardown — mirrors src/paddle_server's lifespan discipline.

# ====== Standard Library Imports ======
import unicodedata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pyfiglet import Figlet

# ====== Local Project Imports ======
from .context import CONTEXT

# Number of discrete startup steps — update when adding or removing steps.
TOTAL_STEPS = 1

logger = loggerplusplus.bind(identifier="MineruServer")


def lifespan() -> Any:
    """
    Return the FastAPI lifespan context manager factory.

    Returns:
        Any: Async context manager suitable for FastAPI's ``lifespan`` parameter.
    """

    def _log_step(step: int, message: str) -> None:
        """Log a numbered startup step to make progress visible in the container logs."""
        logger.info(f"\n[{step}/{TOTAL_STEPS}] {message}...")

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[None]:
        """
        Manage FastAPI startup and shutdown.

        Yields:
            None: Yields control to FastAPI while the service is running.
        """
        _ = app
        try:
            # 1. Print startup banner (strip accents for ASCII console safety)
            app_name = "MinerU Server"
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c
                    for c in unicodedata.normalize("NFD", app_name)
                    if unicodedata.category(c) != "Mn"
                )
            )
            logger.info(f"{banner}")

            # 2. Log runtime configuration, then validate fail-fast. There is no model build here —
            #    MinerU's VLM loads lazily on the first /parse request (see the module docstring).
            _log_step(1, "Runtime configuration")
            logger.info(f"{CONTEXT.CONFIG}")
            CONTEXT.CONFIG.validate()

            logger.info(
                f"\nMinerU Server ready\n"
                f"  model    : {CONTEXT.mineru.MODEL_ID} (loads LAZILY on first /parse)\n"
                f"  backend  : {CONTEXT.CONFIG.MINERU_BACKEND}\n"
                f"  lang     : {CONTEXT.CONFIG.MINERU_LANG}\n"
                f"  require_gpu: {CONTEXT.CONFIG.MINERU_REQUIRE_GPU}\n"
                f"  cache    : {CONTEXT.CONFIG.MINERU_MODEL_CACHE_HOME} "
                f"(source={CONTEXT.CONFIG.MINERU_MODEL_SOURCE})"
            )
            yield

        finally:
            # Shutdown — guard with hasattr so partial startup is still cleaned up gracefully. The
            # model may never have loaded (lazy), and unload() is a safe no-op when it did not.
            logger.info(f"Shutting down MinerU Server...")
            if hasattr(CONTEXT, "mineru"):
                CONTEXT.mineru.unload()

    return _lifespan
