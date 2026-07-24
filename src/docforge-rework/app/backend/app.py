# ====== Code Summary ======
# FastAPI application factory — assembles the app instance and registers all routers.
# No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from fastapi import Depends, FastAPI

# ====== Internal Project Imports ======
# Import config FIRST — it registers the `shared_libs` alias + sys.path. The local imports below
# (auth principal, routers) import `shared_libs.*` at module load, so the alias must exist already.
from config import RUNTIME_CONFIG  # noqa: F401 — side-effect import (path registration)

# ====== Local Project Imports ======
from .libs.auth import authenticate
from .lifespan import lifespan
from .routers import (
    auth_router,
    blobs_router,
    collections_router,
    documents_router,
    explorer_router,
    jobs_router,
    pipelines_router,
    scalar_router,
    search_router,
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

    # The global authN gate — every /api/v1/* route requires a valid bearer key when AUTH_ENABLED
    # (a synthetic full-access principal when it is off). Scalar docs + /openapi.json stay public.
    api_auth = [Depends(authenticate)]

    # Public surfaces — no authentication dependency.
    app.include_router(router=scalar_router, prefix=f"/scalar")

    # API v1 — API-key management (create / list / revoke; gated like the rest).
    app.include_router(router=auth_router, prefix="/api/v1", dependencies=api_auth)

    # API v1 — the pipeline design surface (palette / stages / inspect / edit).
    app.include_router(router=pipelines_router, prefix="/api/v1", dependencies=api_auth)

    # API v1 — the collection contract CRUD (create A→Z, config patching).
    app.include_router(router=collections_router, prefix="/api/v1", dependencies=api_auth)

    # API v1 — admission (upload → enqueue) and live ingestion status.
    app.include_router(router=documents_router, prefix="/api/v1", dependencies=api_auth)
    app.include_router(router=jobs_router, prefix="/api/v1", dependencies=api_auth)

    # API v1 — the document explorer (read surface) and the blob byte stream.
    app.include_router(router=explorer_router, prefix="/api/v1", dependencies=api_auth)
    app.include_router(router=blobs_router, prefix="/api/v1", dependencies=api_auth)

    # API v1 — hybrid retrieval search over a collection.
    app.include_router(router=search_router, prefix="/api/v1", dependencies=api_auth)

    return app


__all__ = ["create_app"]
