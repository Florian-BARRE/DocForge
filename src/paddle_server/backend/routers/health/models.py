# ====== Code Summary ======
# Pydantic response model for the GET /health endpoint.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for the GET /health liveness probe.

    Attributes:
        status (str): "ok" when the pipeline is built and ready; "loading" during startup.
        ready (bool): True only when the PP-StructureV3 pipeline is built and requests will
            be served.
    """

    status: str = Field(..., description="'ok' when ready, 'loading' during startup.")
    ready: bool = Field(..., description="True when the PP-StructureV3 pipeline is built.")
