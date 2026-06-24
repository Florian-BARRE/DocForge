# ====== Code Summary ======
# Route definition for the GET /health liveness probe. Mirrors the TEI /health endpoint so
# DocForge and docker-compose healthchecks can probe the service without client changes.
# Logged at DEBUG only — health is polled frequently and must not flood INFO logs.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter
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
async def health() -> HealthResponse:
    """
    Liveness probe — mirrors TEI's GET /health.

    Returns:
        HealthResponse: Service status and the identities of both loaded models.
    """
    logger.debug(f"GET /health")

    # 1. Return the service status and the model IDs from config (loaded at startup)
    return HealthResponse(
        status="ok",
        embed_model=CONTEXT.CONFIG.BGE_M3_MODEL,
        rerank_model=CONTEXT.CONFIG.BGE_RERANKER_MODEL,
    )
