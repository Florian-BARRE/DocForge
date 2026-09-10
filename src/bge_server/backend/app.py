# ====== Code Summary ======
# FastAPI application factory for the BGE model-suite micro-service.
# Assembles the FastAPI instance, registers all routers, wires the lifespan, and enables (cheap)
# gzip compression on responses. The heavy numeric routes return orjson directly (see
# routers/inference); the app default is left to FastAPI's built-in Pydantic-core serializer. No
# business logic here — only routing configuration and application assembly.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig

# ====== Local Project Imports ======
from .lifespan import lifespan
from .routers import health_router, inference_router

# Below this response size (bytes), gzip's CPU cost isn't worth the saved bandwidth — small
# health/rerank-shape responses skip compression entirely. Dense embed batches (~695 KB for a
# batch of 32) are comfortably above this and compress ~2-3x (float JSON is highly repetitive).
GZIP_MINIMUM_SIZE = 1024


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.

    Registers the health and inference routers at the root (no versioned prefix — TEI contract
    uses bare /health, /embed, /embed_sparse, /rerank without an API prefix). The two heavy
    numeric-matrix routes (/embed, /embed_all) return a hand-built ORJSONResponse, which both
    uses the Rust-backed JSON encoder AND skips the Pydantic response re-validation of every
    float — see routers/inference/router.py. The app default is deliberately NOT changed: this
    FastAPI serializes response_model routes directly via Pydantic-core (its own fast path), so
    forcing ORJSONResponse app-wide would only slow the small model-shaped routes; the numeric
    routes get the win by returning a Response object directly, independent of the app default.
    Response gzip compression is transparent to callers — only the Content-Encoding changes.

    Returns:
        FastAPI: Fully configured application ready for uvicorn.
    """
    app = FastAPI(
        title="BGE model-suite (embed dense+sparse + rerank)",
        version="2.0.0",
        lifespan=lifespan(),
    )

    # Compress large responses (dense/sparse embed batches) transparently. Callers must send
    # `Accept-Encoding: gzip` (httpx/requests do this by default) to receive compressed bodies —
    # this is standard HTTP content negotiation, not a contract change. Level is a config knob
    # (BGE_GZIP_LEVEL) — see config_loader.py for why the default is cheap (1), not zlib's max (9).
    if BgeServerConfig.BGE_GZIP_ENABLED:
        app.add_middleware(
            GZipMiddleware,
            minimum_size=GZIP_MINIMUM_SIZE,
            compresslevel=BgeServerConfig.BGE_GZIP_LEVEL,
        )

    # TEI contract endpoints are at the root level — no /api/v1 prefix.
    # The DocForge `tei` embed provider and `bge_reranker` rerank provider call these paths
    # directly: /embed, /embed_sparse, /rerank, /health.
    app.include_router(health_router)
    app.include_router(inference_router)

    return app


__all__ = ["create_app"]
