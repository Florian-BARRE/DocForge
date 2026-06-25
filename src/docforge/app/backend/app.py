# ====== Code Summary ======
# FastAPI application factory — assembles the app instance and registers all routers.
# No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

# ====== Local Project Imports ======
from .libs.auth import require_principal
from .lifespan import lifespan
from .routers import (
    access_router,
    auth_router,
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
    users_router,
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
    #
    #    Authentication policy (see backend/libs/auth):
    #      - PUBLIC (no auth dependency): health, auth/login, /docs+openapi, the static frontend.
    #        The auth router is mounted bare because its /login route must stay reachable without
    #        credentials; its other routes (/me, /keys) carry their own require_principal dependency.
    #      - PROTECTED: every other router gets a router-level require_principal dependency, so an
    #        unauthenticated request is a 401 before any handler runs. Collection-scoped routers add
    #        per-route require_collection_role(...) checks inside their own router modules.
    #      When AUTH_ENABLED is false, require_principal injects a synthetic root — full rétro-compat.
    auth = [Depends(require_principal)]
    V1 = "/api/v1"
    COL = f"{V1}/collections"
    DOC = f"{COL}/{{collection_id}}/documents"
    # Public surfaces — no authentication dependency.
    app.include_router(router=health_router,    prefix=f"{V1}/health")
    app.include_router(router=auth_router,      prefix=f"{V1}/auth")
    # Protected surfaces — require an authenticated principal.
    app.include_router(router=users_router,      prefix=f"{V1}/users")
    app.include_router(router=discovery_router, prefix=f"{V1}/discovery", dependencies=auth)
    app.include_router(router=collection_router,   prefix=COL, dependencies=auth)
    app.include_router(router=config_router,     prefix=f"{COL}/{{collection_id}}/config", dependencies=auth)
    app.include_router(router=limits_router,      prefix=f"{COL}/{{collection_id}}/limits", dependencies=auth)
    app.include_router(router=access_router,      prefix=f"{COL}/{{collection_id}}/access", dependencies=auth)
    # document_router authenticates PER-ROUTE (each route carries its own require_collection_role,
    # which chains to require_principal) — NOT at include level. This is required because its SSE
    # /stream route needs the header-OR-query SSE dependency, and an include-level header-only
    # require_principal would 401 the header-less EventSource before that route's own dep ran.
    app.include_router(router=document_router,   prefix=DOC)
    app.include_router(router=search_router,     prefix=DOC, dependencies=auth)
    app.include_router(router=files_router,      prefix=f"{DOC}/{{document_id}}", dependencies=auth)
    app.include_router(router=chunks_router,     prefix=f"{DOC}/{{document_id}}/chunks", dependencies=auth)
    # pages_router authenticates PER-ROUTE (same reason as document_router): its screenshot route
    # returns raw PNG bytes loaded via <img>, which cannot send an Authorization header, so it uses
    # the media gate (header OR ?token=). An include-level header-only dep would 401 that <img> load.
    app.include_router(router=pages_router,      prefix=f"{DOC}/{{document_id}}/pages")
    # Global (non collection-scoped) monitoring surfaces — Brique A.
    app.include_router(router=jobs_router,       prefix=f"{V1}/jobs", dependencies=auth)
    # monitoring_router also authenticates PER-ROUTE for the same reason as document_router: its SSE
    # /stream route uses the header-OR-query SSE dependency, incompatible with an include-level
    # header-only gate.
    app.include_router(router=monitoring_router, prefix=f"{V1}/monitoring")

    # 4. Drift guard: every discovery overlay must bind to a real route function (fail fast).
    route_names = {r.endpoint.__name__ for r in app.routes if isinstance(r, APIRoute)}
    validate_overlay_route_names(route_names)

    return app


__all__ = ["create_app"]
