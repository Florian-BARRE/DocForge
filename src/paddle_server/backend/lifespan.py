# ====== Code Summary ======
# Provides the FastAPI lifespan context manager: builds the PPStructureV3 layout pipeline AND the
# PaddleOCR (OCR-only) pipeline at startup, logs the banner and config, and tears both down cleanly
# on exit. Uses a hasattr guard in the finally block so a partial startup never raises during
# teardown — mirrors src/bge_server's lifespan discipline.

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
TOTAL_STEPS = 3

logger = loggerplusplus.bind(identifier="PaddleServer")


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
            app_name = "Paddle Server"
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c
                    for c in unicodedata.normalize("NFD", app_name)
                    if unicodedata.category(c) != "Mn"
                )
            )
            logger.info(f"{banner}")

            # 2. Log runtime configuration, then validate fail-fast BEFORE the slow pipeline
            # build (model download on first run can take minutes) — invalid config must abort
            # startup immediately, not after downloading weights.
            _log_step(1, "Runtime configuration")
            logger.info(f"{CONTEXT.CONFIG}")
            CONTEXT.CONFIG.validate()

            # 3. Build the PP-StructureV3 pipeline — the slow step on first run (model download
            # to the PADDLE_PDX_CACHE_HOME volume + weight load).
            _log_step(2, "Building PP-StructureV3 pipeline")
            CONTEXT.ppstructure.build()

            # 4. Build the PaddleOCR pipeline — the OCR-only capability (a SEPARATE instance from
            # ppstructure; det+rec model download/load on first run).
            _log_step(3, "Building PaddleOCR pipeline")
            CONTEXT.paddleocr.build()

            logger.info(
                f"\nPaddle Server ready\n"
                f"  pipelines: PP-StructureV3 + PaddleOCR\n"
                f"  table    : {CONTEXT.CONFIG.PADDLE_USE_TABLE_RECOGNITION}\n"
                f"  formula  : {CONTEXT.CONFIG.PADDLE_USE_FORMULA_RECOGNITION}\n"
                f"  seal     : {CONTEXT.CONFIG.PADDLE_USE_SEAL_RECOGNITION}\n"
                f"  orient   : {CONTEXT.CONFIG.PADDLE_USE_DOC_ORIENTATION_CLASSIFY}\n"
                f"  unwarp   : False (always)\n"
                f"  ocr lang : {CONTEXT.CONFIG.PADDLE_OCR_LANG} "
                f"(textline_orientation={CONTEXT.CONFIG.PADDLE_OCR_USE_TEXTLINE_ORIENTATION})\n"
                f"  cache    : {CONTEXT.CONFIG.PADDLE_PDX_CACHE_HOME} "
                f"(source={CONTEXT.CONFIG.PADDLE_PDX_MODEL_SOURCE})"
            )
            yield

        finally:
            # Shutdown — guard with hasattr so partial startup is still cleaned up gracefully.
            logger.info(f"Shutting down Paddle Server...")
            if hasattr(CONTEXT, "ppstructure"):
                CONTEXT.ppstructure.unload()
            if hasattr(CONTEXT, "paddleocr"):
                CONTEXT.paddleocr.unload()

    return _lifespan
