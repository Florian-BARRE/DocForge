# ====== Code Summary ======
# FastAPI application factory — assembles the app instance and registers all routers.
# No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI

# ====== Internal Project Imports ======
# Import config FIRST — it registers the `shared_libs` alias + sys.path. The local imports below
# (auth principal, routers) import `shared_libs.*` at module load, so the alias must exist already.
from config import RUNTIME_CONFIG  # noqa: F401 — side-effect import (path registration)

# ====== Local Project Imports ======
from .libs.audit import AuditMiddleware
from .libs.auth import AuthMiddleware
from .libs.idempotency import IdempotencyMiddleware
from .libs.metrics import HttpMetricsMiddleware
from .libs.ratelimit import RateLimitMiddleware
from .libs.requestid import RequestIdMiddleware
from .lifespan import lifespan
from .routers import (
    audit_router,
    auth_router,
    auth_whoami_router,
    blobs_router,
    collections_router,
    corpus_router,
    documents_router,
    explorer_router,
    health_router,
    jobs_router,
    metrics_router,
    pipelines_router,
    scalar_router,
    search_router,
    snippets_router,
    transfers_router,
)


def create_app(
    app_name: str, debug: bool, version: str = "0.1.0", description: str = ""
) -> FastAPI:
    app = FastAPI(
        title=app_name,
        version=version,
        description=description,
        lifespan=lifespan(),
        debug=debug,
    )

    # Middleware nesting is built LIFO: the LAST `add_middleware` call is the OUTERMOST wrapper. CORS
    # is added last (in entrypoint.py), so it stays outermost. The gates below nest, from the
    # request's point of view, as:
    #   CORS → HttpMetrics → RequestId → Auth → RateLimit → Idempotency → Audit → routes.
    #
    # 1. Audit trail (added first → INNERMOST, inside Idempotency). It records one row per mutating
    #    /api/v1 request AFTER it has been routed and answered. Innermost is deliberate: it needs the
    #    principal Auth injected (actor) AND must run only for requests that passed RateLimit — a
    #    throttled 429 is not spammed into the trail, and every audited request has a real route
    #    TEMPLATE for its `path` (never a raw-id path). It still records routed 4xx/5xx. Its write is
    #    fail-safe (errors logged + swallowed) so audit can never affect the request. AUDIT_ENABLED
    #    (default true) toggles it; off → transparent passthrough. Being INNER to Idempotency, an
    #    idempotent REPLAY (which short-circuits above Audit) is NOT re-audited: the operation was
    #    already audited on its one real execution, so the trail carries no duplicate replay rows.
    app.add_middleware(AuditMiddleware)

    # 2. Idempotency (added → inner of RateLimit, OUTER of Audit). On an eligible mutating request that
    #    carries an `Idempotency-Key`, it dedups by (actor, route, key): first request runs once + the
    #    response is cached; retries replay it. It needs the principal (actor scope) so it sits inner to
    #    Auth; it sits INNER to RateLimit so a replay still costs the caller budget (no replay-spam
    #    bypass); it sits OUTER to Audit so a replay is not re-audited (see above). ON by default but
    #    only ever engages when the header is present on an allow-listed endpoint → otherwise passthrough.
    app.add_middleware(IdempotencyMiddleware)

    # 3. Rate limiter (added → inner of Auth, outer of Idempotency). It runs AFTER AuthMiddleware has
    #    resolved the principal, so it can key by the caller's API key when auth is on (else by client
    #    IP). OFF by default → transparent. Only /api/v1/* (minus the job-poll/SSE subtree) is limited.
    app.add_middleware(RateLimitMiddleware)

    # 4. The global authN gate — a PURE ASGI middleware that runs BEFORE FastAPI parses the request
    #    body, so a missing/revoked bearer yields 401 (never a 422-before-401 on a malformed body). It
    #    gates every /api/v1/* path and injects the principal for the per-endpoint `require` authZ gate
    #    AND for the rate limiter's identity keying AND for the audit actor. With AUTH_ENABLED=false it
    #    stays transparent (synthetic root). Scalar + /openapi.json + /metrics stay public (outside /api/v1).
    app.add_middleware(AuthMiddleware)

    # 5. Correlation id (added here → OUTER to Auth + RateLimit, INNER to HttpMetrics). It must be
    #    outside both gates so their short-circuit 401/429 responses are emitted INSIDE the correlation
    #    context (those log lines carry the id) AND still get the `X-Request-ID` header stamped on the
    #    way out. Always-on, zero-config: it binds an inbound or freshly-minted id for the request.
    app.add_middleware(RequestIdMiddleware)

    # 6. HTTP request metrics (added last → OUTERMOST, inside CORS). Being outer to the
    #    gates, it counts 401/429 responses too (those short-circuit before routing, so their route
    #    label is "__unmatched__"). Passive — it only records; GET /metrics serves what it collects.
    app.add_middleware(HttpMetricsMiddleware)

    # Public surfaces — no authentication dependency (both live outside /api/v1, so the authN
    # middleware leaves them untouched: scalar docs + the orchestration liveness probe).
    app.include_router(router=scalar_router, prefix=f"/scalar")
    app.include_router(router=health_router)

    # Ops scrape surface — Prometheus /metrics, also outside /api/v1 (auth- and rate-limit-exempt by
    # placement; network-restrict it at the proxy). Excluded from the OpenAPI schema.
    app.include_router(router=metrics_router)

    # API v1 — API-key management (create / list / revoke; gated like the rest).
    app.include_router(router=auth_router, prefix="/api/v1")
    app.include_router(router=auth_whoami_router, prefix="/api/v1")

    # API v1 — the pipeline design surface (palette / stages / inspect / edit).
    app.include_router(router=pipelines_router, prefix="/api/v1")

    # API v1 — the collection contract CRUD (create A→Z, config patching).
    app.include_router(router=collections_router, prefix="/api/v1")

    # API v1 — admission (upload → enqueue) and live ingestion status.
    app.include_router(router=documents_router, prefix="/api/v1")
    app.include_router(router=jobs_router, prefix="/api/v1")

    # API v1 — collection export/import (async bundle transfer + status + download delivery).
    app.include_router(router=transfers_router, prefix="/api/v1")

    # API v1 — granular collection-config snippets (synchronous export/apply of one config slice).
    app.include_router(router=snippets_router, prefix="/api/v1")

    # API v1 — the document explorer (read surface) and the blob byte stream.
    app.include_router(router=explorer_router, prefix="/api/v1")
    app.include_router(router=blobs_router, prefix="/api/v1")

    # API v1 — the large-scale corpus grid (query + bulk delete/enable/reingest).
    app.include_router(router=corpus_router, prefix="/api/v1")

    # API v1 — hybrid retrieval search over a collection.
    app.include_router(router=search_router, prefix="/api/v1")

    # API v1 — the append-only audit trail read surface (ROOT/full-access only).
    app.include_router(router=audit_router, prefix="/api/v1")

    return app


__all__ = ["create_app"]
