# ====== Code Summary ======
# Pydantic response model for the GET /health endpoint.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for the GET /health liveness probe.

    Attributes:
        status (str): "ok" when both pipelines are built and ready; "loading" during startup.
        ready (bool): True only when BOTH the PP-StructureV3 layout pipeline and the PaddleOCR
            pipeline are built and requests will be served.
    """

    status: str = Field(..., description="'ok' when ready, 'loading' during startup.")
    ready: bool = Field(
        ..., description="True when both the PP-StructureV3 and PaddleOCR pipelines are built."
    )
