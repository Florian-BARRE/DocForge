# ====== Code Summary ======
# The self-introspection route — GET /auth/whoami reports the CALLING token's own access (its coarse
# capabilities + collection scope) so a client, an MCP agent especially, can discover what it may do
# without probing endpoints and collecting 403s. It authenticates like every route but requires NO
# specific capability (even a search-only key must be able to ask "what am I"). A NULL-permissions or
# auth-disabled principal reports full, unscoped access.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends

# ====== Internal Project Imports ======
from ...libs.auth import AuthPrincipal, Capability
from ...libs.auth.dependency import authenticate
from ...libs.auth.permissions import KeyPermissions
from ...utils.error_handling import auto_handle_errors
from .models import WhoAmI

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/whoami", response_model=WhoAmI)
@auto_handle_errors
async def whoami(principal: AuthPrincipal = Depends(authenticate)) -> WhoAmI:
    """
    Report the calling token's capabilities and collection scope — what it is allowed to do.

    Returns:
        WhoAmI: The resolved access (full/unscoped for a root or auth-off principal, else the key's
        parsed capabilities + collection scope).
    """
    # 1. Root / auth-off: full, unscoped access — every capability, every collection.
    if principal.is_full_access or principal.key is None:
        return WhoAmI(
            authenticated=True,
            root=True,
            capabilities=[capability.value for capability in Capability],
            collections=["*"],
        )
    # 2. A scoped key: report exactly the capabilities + collections it was granted.
    permissions = KeyPermissions.model_validate(principal.key.permissions)
    return WhoAmI(
        authenticated=True,
        root=False,
        capabilities=[capability.value for capability in permissions.capabilities],
        collections=list(permissions.collections),
    )


__all__ = ["router"]
