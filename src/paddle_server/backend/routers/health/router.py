# ====== Code Summary ======
# Route definition for the GET /health liveness probe. Mirrors src/bge_server's readiness-gate
# convention: HTTP 503 (status="loading", ready=False) while the PP-StructureV3 pipeline is still
# building, so compose healthchecks and the DocForge worker's EndpointReachability preflight never
# hit an unready container. Logged at DEBUG only — health is polled frequently.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Response
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors

# ====== Local Project Imports ======
from .models import HealthResponse

router = APIRouter()

# DEBUG-level logger — health is polled by compose/docforge at high frequency; using INFO
# here would flood the logs with noise that obscures actual lifecycle events.
logger = loggerplusplus.bind(identifier="HealthRouter")


@router.get("/health", response_model=HealthResponse)
@auto_handle_errors
async def health(response: Response) -> HealthResponse:
    """
    Liveness + readiness probe.

    Returns HTTP 200 with status="ok" and ready=True once the PP-StructureV3 pipeline is built.
    Returns HTTP 503 with status="loading" and ready=False while startup is in progress.

    Args:
        response (Response): FastAPI response object used to set the HTTP status code.

    Returns:
        HealthResponse: Service status and readiness flag.
    """
    logger.debug(f"GET /health")

    pipeline_ready = hasattr(CONTEXT, "ppstructure") and CONTEXT.ppstructure.ready

    if not pipeline_ready:
        response.status_code = 503
        return HealthResponse(status="loading", ready=False)

    return HealthResponse(status="ok", ready=True)
