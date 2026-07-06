# ====== Code Summary ======
# FastAPI application factory — assembles the app instance and registers all routers.
# No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI

# ====== Local Project Imports ======
from .lifespan import lifespan
from .routers import (
    blobs_router,
    collections_router,
    documents_router,
    explorer_router,
    jobs_router,
    pipelines_router,
    scalar_router,
)


def create_app(
        app_name: str,
        debug: bool,
        version: str = "0.1.0",
        description: str = ""
) -> FastAPI:
    app = FastAPI(
        title=app_name,
        version=version,
        description=description,
        lifespan=lifespan(),
        debug=debug,
    )

    # Public surfaces — no authentication dependency.
    app.include_router(router=scalar_router, prefix=f"/scalar")

    # API v1 — the pipeline design surface (palette / stages / inspect / edit).
    app.include_router(router=pipelines_router, prefix="/api/v1")

    # API v1 — the collection contract CRUD (create A→Z, config patching).
    app.include_router(router=collections_router, prefix="/api/v1")

    # API v1 — admission (upload → enqueue) and live ingestion status.
    app.include_router(router=documents_router, prefix="/api/v1")
    app.include_router(router=jobs_router, prefix="/api/v1")

    # API v1 — the document explorer (read surface) and the blob byte stream.
    app.include_router(router=explorer_router, prefix="/api/v1")
    app.include_router(router=blobs_router, prefix="/api/v1")

    return app


__all__ = ["create_app"]
