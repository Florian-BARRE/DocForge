# ====== Code Summary ======
# FastAPI application factory for the PP-StructureV3 layout-parsing micro-service.
# Assembles the FastAPI instance, registers all routers, wires the lifespan, and enables gzip
# compression on responses. No business logic here — only routing configuration and application
# assembly.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

# ====== Local Project Imports ======
from .lifespan import lifespan
from .routers import health_router, layout_parsing_router, ocr_router

# Below this response size (bytes), gzip's CPU cost isn't worth the saved bandwidth — small
# /health responses skip compression entirely. A multi-page /layout-parsing response (reading-
# ordered blocks + table HTML) is comfortably above this and compresses well (repetitive JSON).
GZIP_MINIMUM_SIZE = 1024


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.

    Registers the health, layout-parsing and OCR routers at the root (no versioned prefix — matches
    the sibling bge_server convention). Response gzip compression is transparent to callers — it
    does not change any API shape, only the Content-Encoding of large responses.

    Returns:
        FastAPI: Fully configured application ready for uvicorn.
    """
    app = FastAPI(
        title="PaddleOCR PP-StructureV3 layout-parsing service",
        version="1.0.0",
        lifespan=lifespan(),
    )

    # Compress large responses (multi-page block lists with table HTML) transparently. Callers
    # must send `Accept-Encoding: gzip` (httpx/requests do this by default) to receive
    # compressed bodies — this is standard HTTP content negotiation, not a contract change.
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)

    app.include_router(health_router)
    app.include_router(layout_parsing_router)
    app.include_router(ocr_router)

    return app


__all__ = ["create_app"]
