# ====== Code Summary ======
# The /metrics router — the Prometheus scrape endpoint. It is registered OUTSIDE the /api/v1 prefix, so
# the authN middleware (which only gates /api/v1/*) never touches it (scrapers carry no bearer) and the
# rate limiter never touches it either. It returns the Prometheus text/plain exposition (not a JSON
# model) — hence no `response_model` (a Pydantic model would force JSON) — and is registered with
# `include_in_schema=False`, so it never enters the OpenAPI document and the SDK↔backend parity
# snapshot is unaffected. Gated by METRICS_ENABLED (404 when off) so an operator can hide it live.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
@auto_handle_errors
async def metrics() -> Response:
    """
    Serve the Prometheus exposition (HTTP series + DocForge infra gauges) as text/plain.

    Auth-exempt by placement (outside /api/v1); operators must network-restrict this endpoint at the
    proxy/firewall. Returns 404 when METRICS_ENABLED is false, so the endpoint can be hidden without
    unwiring it.

    Returns:
        Response: The Prometheus text exposition with the exposition-format media type.
    """
    # 1. Disabled → behave as if the endpoint does not exist (operator opt-out via config).
    if not RUNTIME_CONFIG.METRICS_ENABLED:
        raise HTTPException(status_code=404, detail="Metrics are disabled.")

    # 2. Refresh the infra gauges (best-effort) and render the whole registry as Prometheus text.
    payload = await CONTEXT.metrics_service.render()
    return Response(content=payload, media_type=CONTEXT.metrics_service.content_type)


__all__ = ["router"]
