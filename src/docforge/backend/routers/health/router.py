# ====== Code Summary ======
# Health check router — returns service status, API version, and GPU info.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter

# ====== Internal Project Imports ======
from ...context import CONTEXT
from ...libs.utils.error_handling import auto_handle_errors
from .models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/ping", response_model=HealthResponse)
@auto_handle_errors
async def ping() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        HealthResponse: Service status, version, and GPU availability.
    """
    # 1. Build and return the health response
    return HealthResponse(
        status="ok",
        version=CONTEXT.RUNTIME_CONFIG.APP_VERSION,
        gpu_available=CONTEXT.device_manager.gpu_available,
        gpu_name=CONTEXT.device_manager.gpu_name,
    )
