# ====== Code Summary ======
# Pydantic models for the health check router.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: str = Field(..., description="Service status: 'ok' when healthy.")
    version: str = Field(..., description="DocForge API version.")
    gpu_available: bool = Field(..., description="True if a GPU was detected at startup.")
    gpu_name: str | None = Field(default=None, description="GPU device name, if available.")
