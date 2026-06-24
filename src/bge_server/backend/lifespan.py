# ====== Code Summary ======
# Provides the FastAPI lifespan context manager: loads BGE models at startup, logs the banner and
# config, and unloads models cleanly on shutdown. Uses hasattr guards in the finally block so a
# partial startup never raises during teardown.

# ====== Standard Library Imports ======
import unicodedata
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pyfiglet import Figlet

# ====== Local Project Imports ======
from .context import CONTEXT

# Number of discrete startup steps — update when adding or removing steps.
TOTAL_STEPS = 2

logger = loggerplusplus.bind(identifier="BGEServer")


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
            app_name = "BGE Server"
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c
                    for c in unicodedata.normalize("NFD", app_name)
                    if unicodedata.category(c) != "Mn"
                )
            )
            logger.info(f"{banner}")

            # 2. Log runtime configuration so env-overrides are visible at boot, then
            # validate it fail-fast BEFORE the slow model load — an invalid BGE_DEVICE policy
            # must abort startup immediately, not after downloading ~4.4 GiB of weights.
            _log_step(1, "Runtime configuration")
            logger.info(f"{CONTEXT.CONFIG}")
            CONTEXT.CONFIG.validate()

            # 3. Load BGE models — this is the slow step (~30–120 s on first run, weights download)
            _log_step(2, "Loading BGE models")
            CONTEXT.bge_models.load()

            # 4. Service is ready — log a structured boot summary and yield to FastAPI.
            # resolved_device is set by load(); it reflects the actual device in use
            # (after applying the BGE_DEVICE policy + CUDA availability check).
            # BGE_FP16 from config is the *requested* value; bge_models.use_fp16 is the
            # *gated* value (forced false on CPU even if BGE_FP16=true was set).
            resolved_device = CONTEXT.bge_models.resolved_device or "unknown"
            gated_fp16 = CONTEXT.bge_models.use_fp16
            logger.info(
                f"\nBGE Server ready\n"
                f"  embed   : {CONTEXT.CONFIG.BGE_M3_MODEL}\n"
                f"  rerank  : {CONTEXT.CONFIG.BGE_RERANKER_MODEL}\n"
                f"  policy  : {CONTEXT.CONFIG.BGE_DEVICE} -> device: {resolved_device}\n"
                f"  fp16    : requested={CONTEXT.CONFIG.BGE_FP16}, active={gated_fp16}\n"
                f"  max_len : {CONTEXT.CONFIG.BGE_M3_MAX_LENGTH}"
            )
            yield

        finally:
            # Shutdown — guard with hasattr so partial startup is still cleaned up gracefully
            logger.info(f"Shutting down BGE Server...")
            if hasattr(CONTEXT, "bge_models"):
                CONTEXT.bge_models.unload()

    return _lifespan
