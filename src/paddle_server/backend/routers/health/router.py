# ====== Code Summary ======
# Route definition for the GET /health liveness probe. Mirrors src/bge_server's readiness-gate
# convention: HTTP 503 (status="loading", ready=False) while EITHER pipeline (PP-StructureV3 layout
# or PaddleOCR) is still building, so compose healthchecks and the DocForge worker's
# EndpointReachability preflight (both the pp_structure parser AND the paddle OCR node probe this
# route) never hit an unready container. Logged at DEBUG only — health is polled frequently.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Response
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.cpu_features import CpuFeatures
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

    Returns HTTP 200 with status="ok" and ready=True once BOTH the PP-StructureV3 layout pipeline
    and the PaddleOCR pipeline are built AND the host can actually run inference. Returns HTTP 503
    with status="unhealthy" when the CPU lacks AVX (PaddlePaddle would SIGILL on the first real
    inference — pipelines build fine, so this is the ONLY thing that stops the container advertising
    a readiness it cannot honor), or status="loading" while either pipeline is still starting up.

    Args:
        response (Response): FastAPI response object used to set the HTTP status code.

    Returns:
        HealthResponse: Service status and readiness flag.
    """
    logger.debug(f"GET /health")

    # 1. Hard gate: a CPU without AVX builds the pipelines fine but SIGILLs on the first inference.
    #    Report UNHEALTHY up front (checked before pipeline readiness) so the container never claims
    #    a readiness it cannot honor. Cheap + cached — see CpuFeatures.
    if not CpuFeatures.supports_avx():
        response.status_code = 503
        return HealthResponse(
            status="unhealthy",
            ready=False,
            detail="CPU lacks AVX support required by PaddlePaddle; inference would crash.",
        )

    # 2. Readiness: both pipelines must be built before the sidecar serves any request.
    pipeline_ready = (
        hasattr(CONTEXT, "ppstructure")
        and CONTEXT.ppstructure.ready
        and hasattr(CONTEXT, "paddleocr")
        and CONTEXT.paddleocr.ready
    )

    if not pipeline_ready:
        response.status_code = 503
        return HealthResponse(status="loading", ready=False, detail="Pipelines are still building.")

    return HealthResponse(status="ok", ready=True)
