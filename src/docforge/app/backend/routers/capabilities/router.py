# ====== Code Summary ======
# The public capabilities discovery endpoint — a /health-style self-description of what THIS DocForge
# deployment can actually do right now: running version, auth state, GPU presence, the optional
# sidecars (short-cached reachability + what each unlocks) and the available pipeline kinds per family.
# It lives OUTSIDE the /api/v1 prefix (registered at the bare origin, exactly like /health and
# /metrics), so the authN middleware — which only gates /api/v1/* — never touches it: discovery stays
# credential-free even when AUTH_ENABLED is true. All work lives in CONTEXT.capabilities_service.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter

# ====== Internal Project Imports ======
from ...context import CONTEXT
from ...libs.capabilities import CapabilitiesResponse
from ...utils.error_handling import auto_handle_errors

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
@auto_handle_errors
async def capabilities() -> CapabilitiesResponse:
    """
    Report what this deployment can do right now (public, no auth — mirrors /health placement).

    Returns:
        CapabilitiesResponse: Running version, auth state, derived GPU presence, the infra stores +
        optional sidecars (cached reachability + what each unlocks), and the available pipeline kinds
        per family.
    """
    # 1. Delegate to the service — it owns the requirement map + the short-cached sidecar probe.
    return await CONTEXT.capabilities_service.describe()


__all__ = ["router"]
