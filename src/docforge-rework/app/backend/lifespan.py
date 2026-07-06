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

# ====== Local Project Imports ======
from .context import CONTEXT

# Total number of startup steps — update when adding/removing steps.
TOTAL_STEPS = 2


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

            # 2. Log the runtime configuration (secrets are masked by configplusplus).
            log_step(1, "Runtime configuration")
            CONTEXT.logger.info(CONTEXT.RUNTIME_CONFIG)

            # 3. The design-surface services (stateless — instantiated in entrypoint.py).
            log_step(2, "Pipeline design surface")
            CONTEXT.logger.info(
                f"Builder/validator ready — palette, mechanics and artefacts are "
                f"served from the node registry"
            )

            # 4. Yield — the app is now serving.
            yield

        finally:
            # Shutdown in reverse order; nothing stateful to close yet.
            CONTEXT.logger.info(f"Shutting down...")

    return _lifespan


__all__ = ["lifespan"]
