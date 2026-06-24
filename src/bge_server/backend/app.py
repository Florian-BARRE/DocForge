# ====== Code Summary ======
# FastAPI application factory for the BGE model-suite micro-service.
# Assembles the FastAPI instance, registers all routers, and wires the lifespan. No business
# logic here — only routing configuration and application assembly.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI

# ====== Local Project Imports ======
from .lifespan import lifespan
from .routers import health_router, inference_router


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.

    Registers the health and inference routers at the root (no versioned prefix — TEI contract
    uses bare /health, /embed, /embed_sparse, /rerank without an API prefix).

    Returns:
        FastAPI: Fully configured application ready for uvicorn.
    """
    app = FastAPI(
        title="BGE model-suite (embed dense+sparse + rerank)",
        version="2.0.0",
        lifespan=lifespan(),
    )

    # TEI contract endpoints are at the root level — no /api/v1 prefix.
    # The DocForge `tei` embed provider and `bge_reranker` rerank provider call these paths
    # directly: /embed, /embed_sparse, /rerank, /health.
    app.include_router(health_router)
    app.include_router(inference_router)

    return app


__all__ = ["create_app"]
