# ====== Code Summary ======
# The health router — a PUBLIC liveness/readiness endpoint for orchestration. It lives OUTSIDE the
# /api/v1 prefix, so the authN middleware (which only gates /api/v1/*) never touches it: probes stay
# credential-free even when AUTH_ENABLED is true. It reports process liveness only — no store I/O.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter

# ====== Local Project Imports ======
from ...utils.error_handling import auto_handle_errors
from .models import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, include_in_schema=False)
@auto_handle_errors
async def health() -> HealthStatus:
    """
    Report process liveness for orchestration probes (no store access, always public).

    Returns:
        HealthStatus: A static ``{"status": "ok"}`` payload with HTTP 200.
    """
    # 1. Liveness only — reaching this handler is itself the proof the app is serving.
    return HealthStatus(status="ok")


__all__ = ["router"]
