# ====== Code Summary ======
# Defines the shared application context (typed service locator) used across all routes and the
# lifespan. Type annotations only — all values are assigned at startup in entrypoint.py or
# lifespan.py. Access via CONTEXT.attribute_name anywhere in the codebase.

# ====== Internal Project Imports ======
from config_loader import PaddleServerConfig
from libs.paddleocr import PaddleOcrService
from libs.ppstructure import PpStructureService


class CONTEXT:
    """
    Shared application context for the PaddleOCR PP-StructureV3 + OCR micro-service.

    A typed static service locator — never instantiated. All attributes are set during
    startup (entrypoint.py injects config; lifespan.py injects the loaded pipeline services).
    """

    # ── Configuration ────────────────────────────────────────────────────────────
    CONFIG: type[PaddleServerConfig]

    # ── PP-StructureV3 pipeline service ─────────────────────────────────────────────
    # Holds the built PPStructureV3 pipeline after lifespan startup completes. Owns the
    # asyncio.Lock that serializes every predict() call (PaddlePaddle is not thread-safe).
    ppstructure: PpStructureService

    # ── PaddleOCR (OCR-only) pipeline service ────────────────────────────────────────
    # Holds the built PaddleOCR text det+rec pipeline — a SEPARATE instance from ppstructure
    # (pure OCR capability, no layout). Owns its own predict lock.
    paddleocr: PaddleOcrService
