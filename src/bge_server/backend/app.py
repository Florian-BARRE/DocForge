# ====== Code Summary ======
# FastAPI application factory for the BGE model-suite micro-service.
# Assembles the FastAPI instance, registers all routers, wires the lifespan, and enables gzip
# compression on responses. No business logic here — only routing configuration and application
# assembly.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

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
    uses bare /health, /embed, /embed_sparse, /rerank without an API prefix). Response gzip
    compression is transparent to callers — it does not change any API shape, only the
    Content-Encoding of large responses.

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
    # this is standard HTTP content negotiation, not a contract change.
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)

    # TEI contract endpoints are at the root level — no /api/v1 prefix.
    # The DocForge `tei` embed provider and `bge_reranker` rerank provider call these paths
    # directly: /embed, /embed_sparse, /rerank, /health.
    app.include_router(health_router)
    app.include_router(inference_router)

    return app


__all__ = ["create_app"]
