# ====== Code Summary ======
# Route definition for the GET /health liveness probe. Mirrors the TEI /health endpoint so
# DocForge and docker-compose healthchecks can probe the service without client changes.
# Logged at DEBUG only — health is polled frequently and must not flood INFO logs.
#
# Readiness gate: the endpoint returns HTTP 503 (status="loading", ready=False) while the
# BGE models are still loading. This prevents compose dependents and the DocForge worker
# from sending inference requests to an unready container — they will retry the healthcheck
# (compose: start_period=300s covers the full weight download) and the 503 surfaces clearly
# in logs instead of an opaque "model not yet loaded" RuntimeError mid-request.

# ====== Standard Library Imports ======
from fastapi import APIRouter, Response

# ====== Third-Party Library Imports ======
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
    Liveness + readiness probe — mirrors TEI's GET /health.

    Returns HTTP 200 with status="ok" and ready=True once both BGE models are fully loaded.
    Returns HTTP 503 with status="loading" and ready=False while startup is in progress, so
    compose healthchecks and clients can distinguish a booting container from a healthy one.

    Args:
        response (Response): FastAPI response object used to set the HTTP status code.

    Returns:
        HealthResponse: Service status, readiness flag, and model identities.
    """
    logger.debug(f"GET /health")

    # 1. Check whether both models have been loaded by inspecting the private sentinel.
    # BgeModelsService._embed_model is None until load() completes; using hasattr guards
    # against the race where bge_models itself is not yet set on CONTEXT (very early boot).
    models_ready = (
        hasattr(CONTEXT, "bge_models")
        and CONTEXT.bge_models._embed_model is not None  # noqa: SLF001
        and CONTEXT.bge_models._reranker is not None  # noqa: SLF001
    )

    # 2. Return 503 while loading so compose/docforge treat the container as not-yet-ready
    if not models_ready:
        response.status_code = 503
        return HealthResponse(
            status="loading",
            ready=False,
            embed_model=CONTEXT.CONFIG.BGE_M3_MODEL,
            rerank_model=CONTEXT.CONFIG.BGE_RERANKER_MODEL,
        )

    # 3. Both models loaded — return 200 OK
    return HealthResponse(
        status="ok",
        ready=True,
        embed_model=CONTEXT.CONFIG.BGE_M3_MODEL,
        rerank_model=CONTEXT.CONFIG.BGE_RERANKER_MODEL,
    )
