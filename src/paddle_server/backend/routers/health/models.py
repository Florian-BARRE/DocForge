# ====== Code Summary ======
# Pydantic response model for the GET /health endpoint.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for the GET /health liveness probe.

    Attributes:
        status (str): "ok" when both pipelines are built and ready; "loading" during startup;
            "unhealthy" when the host cannot serve inference at all (e.g. a CPU without AVX, on
            which PaddlePaddle SIGILLs at the first inference).
        ready (bool): True only when BOTH the PP-StructureV3 layout pipeline and the PaddleOCR
            pipeline are built AND the host can actually run inference.
        detail (str | None): Human-readable reason when not ready (diagnostics only); None on "ok".
    """

    status: str = Field(
        ...,
        description="'ok' when ready, 'loading' during startup, 'unhealthy' when unserviceable.",
    )
    ready: bool = Field(
        ...,
        description="True when both pipelines are built and the host can run inference.",
    )
    detail: str | None = Field(
        default=None, description="Reason the service is not ready; None when status is 'ok'."
    )
