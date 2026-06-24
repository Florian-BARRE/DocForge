# ====== Code Summary ======
# FastAPI application factory — assembles the app instance and registers all routers.
# No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

# ====== Local Project Imports ======
from .lifespan import lifespan
from .routers import (
    chunks_router,
    collection_router,
    config_router,
    discovery_router,
    document_router,
    files_router,
    health_router,
    jobs_router,
    limits_router,
    monitoring_router,
    pages_router,
    search_router,
)
from .routers.discovery.overlays import validate_overlay_route_names


def create_app(app_name: str, debug: bool, version: str = "0.1.0", description: str = "") -> FastAPI:
    """
    Create and configure the FastAPI application.

    Registers all API routers under the /api/v1 prefix.
    The lifespan context manager handles service startup and graceful shutdown.

    Args:
        app_name (str): Application title shown in OpenAPI docs.
        debug (bool): Enable debug mode (full traceback in 500 responses).
        version (str): API version string shown in OpenAPI docs.
        description (str): Short description shown in OpenAPI docs.

    Returns:
        FastAPI: Fully configured application instance.
    """
    # 1. Instantiate the FastAPI app with lifespan and metadata
    app = FastAPI(
        title=app_name,
        version=version,
        description=description,
        lifespan=lifespan(),
        debug=debug,
    )

    # 2. Scalar — modern API reference UI at /scalar (CDN, no extra dependency)
    @app.get("/scalar", include_in_schema=False, response_class=HTMLResponse)
    async def scalar_ui() -> HTMLResponse:
        return HTMLResponse(content=f"""<!doctype html>
<html><head><title>{app_name} — API Reference</title><meta charset="utf-8"/></head>
<body>
  <script id="api-reference" data-url="/openapi.json"></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body></html>""")

    # 3. Register all routers — the full URL structure is defined here, once.
    #    Each router uses only relative leaf paths in its decorators.
    V1 = "/api/v1"
    COL = f"{V1}/collections"
    DOC = f"{COL}/{{collection_id}}/documents"
    app.include_router(router=health_router,    prefix=f"{V1}/health")
    app.include_router(router=discovery_router, prefix=f"{V1}/discovery")
    app.include_router(router=collection_router,   prefix=COL)
    app.include_router(router=config_router,     prefix=f"{COL}/{{collection_id}}/config")
    app.include_router(router=limits_router,      prefix=f"{COL}/{{collection_id}}/limits")
    app.include_router(router=document_router,   prefix=DOC)
    app.include_router(router=search_router,     prefix=DOC)
    app.include_router(router=files_router,      prefix=f"{DOC}/{{document_id}}")
    app.include_router(router=chunks_router,     prefix=f"{DOC}/{{document_id}}/chunks")
    app.include_router(router=pages_router,      prefix=f"{DOC}/{{document_id}}/pages")
    # Global (non collection-scoped) monitoring surfaces — Brique A.
    app.include_router(router=jobs_router,       prefix=f"{V1}/jobs")
    app.include_router(router=monitoring_router, prefix=f"{V1}/monitoring")

    # 4. Drift guard: every discovery overlay must bind to a real route function (fail fast).
    route_names = {r.endpoint.__name__ for r in app.routes if isinstance(r, APIRoute)}
    validate_overlay_route_names(route_names)

    return app


__all__ = ["create_app"]
