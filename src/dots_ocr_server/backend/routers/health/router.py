# ====== Code Summary ======
# Route definition for the GET /health liveness probe. Mirrors src/mineru_server's readiness-gate
# convention: HTTP 503 (status="unhealthy") when DOTS_OCR_REQUIRE_GPU is set and no CUDA GPU is visible,
# because dots.ocr's VLM requires CUDA (it would fail at model load on CPU). The dots.ocr model itself
# loads lazily on the first /parse, so readiness is NOT gated on a pre-loaded model — only on the host
# being able to run inference at all. The DocForge worker's EndpointReachability preflight (the dots_ocr
# parser node) probes this route. Logged at DEBUG only — health is polled frequently.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Response
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.libs.utils.gpu_features import GpuFeatures

# ====== Local Project Imports ======
from .models import HealthResponse

router = APIRouter()

# DEBUG-level logger — health is polled by compose/docforge at high frequency; using INFO here would
# flood the logs with noise that obscures actual lifecycle events.
logger = loggerplusplus.bind(identifier="HealthRouter")


@router.get("/health", response_model=HealthResponse)
@auto_handle_errors
async def health(response: Response) -> HealthResponse:
    """
    Liveness + readiness probe.

    Returns HTTP 200 (status="ok", ready=True) once the host can serve dots.ocr inference. Returns HTTP
    503 (status="unhealthy") when DOTS_OCR_REQUIRE_GPU is set and no CUDA GPU is visible — dots.ocr's
    VLM requires CUDA, so the container never advertises a readiness it cannot honor.

    Args:
        response (Response): FastAPI response object used to set the HTTP status code.

    Returns:
        HealthResponse: Service status and readiness flag.
    """
    logger.debug(f"GET /health")

    # 1. Hard gate: the dots.ocr VLM requires CUDA. When required but no GPU is visible, report
    #    UNHEALTHY up front so the container never claims a readiness it cannot honor. Cheap + cached.
    if CONTEXT.CONFIG.DOTS_OCR_REQUIRE_GPU and not GpuFeatures.cuda_available():
        response.status_code = 503
        return HealthResponse(
            status="unhealthy",
            ready=False,
            detail="No CUDA GPU visible; dots.ocr's VLM requires one.",
            device=GpuFeatures.device(),
        )

    return HealthResponse(status="ok", ready=True, device=GpuFeatures.device())
