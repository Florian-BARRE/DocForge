# ====== Code Summary ======
# Pydantic response model for the GET /health endpoint.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for the GET /health liveness probe.

    Attributes:
        status (str): "ok" when the host can serve MinerU inference; "unhealthy" when it cannot (no
            CUDA GPU visible while MINERU_REQUIRE_GPU is set — the MinerU2.5-Pro VLM requires CUDA).
        ready (bool): True when the host can run inference (the model itself loads lazily on the first
            /parse, so readiness is gated on the GPU, not on the model being pre-loaded).
        detail (str | None): Human-readable reason when not ready (diagnostics only); None on "ok".
        device (str): Runtime compute device — "cuda" when a GPU is present, else "cpu". Read by the
            DocForge app's GET /capabilities probe to decide whether this sidecar runs on a GPU.
    """

    status: str = Field(
        ..., description="'ok' when serviceable, 'unhealthy' when no CUDA GPU is available."
    )
    ready: bool = Field(..., description="True when the host can run MinerU inference.")
    detail: str | None = Field(
        default=None, description="Reason the service is not ready; None when status is 'ok'."
    )
    device: str = Field(
        ..., description="Runtime compute device: 'cuda' when a GPU is present, else 'cpu'."
    )


__all__ = ["HealthResponse"]
