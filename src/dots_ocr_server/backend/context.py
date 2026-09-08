# ====== Code Summary ======
# Defines the shared application context (typed service locator) used across all routes and the
# lifespan. Type annotations only — all values are assigned at startup in entrypoint.py or lifespan.py.
# Access via CONTEXT.attribute_name anywhere in the codebase.

# ====== Internal Project Imports ======
from config_loader import DotsOcrServerConfig
from libs.dots_ocr import DotsOcrService


class CONTEXT:
    """
    Shared application context for the dots.ocr VLM parse micro-service.

    A typed static service locator — never instantiated. All attributes are set during startup
    (entrypoint.py injects config + the service; lifespan.py validates config).
    """

    # ── Configuration ────────────────────────────────────────────────────────────
    CONFIG: type[DotsOcrServerConfig]

    # ── dots.ocr parse service ───────────────────────────────────────────────────
    # Holds the dots.ocr per-element layout VLM parse pipeline. The heavy transformers model loads LAZILY inside
    # the engine on the first /parse request (not at lifespan startup), so a deployment that never
    # escalates to this parser never pays the model download/load. Owns the asyncio.Lock that serializes
    # every parse.
    dots_ocr: DotsOcrService
