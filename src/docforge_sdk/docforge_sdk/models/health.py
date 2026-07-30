# ====== Code Summary ======
# Response model for the health resource — the minimal liveness payload the bare-root /health probe
# returns, mirrored field-for-field from the DocForge backend router model.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """
    The public health probe payload.

    Attributes:
        status (str): Liveness marker — always ``"ok"`` when the app is serving.
    """

    status: str = Field(description="Liveness marker — always 'ok' when the app is serving.")


__all__ = ["HealthStatus"]
