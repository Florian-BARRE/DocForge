# ====== Code Summary ======
# The health endpoint's response model — a minimal liveness/readiness payload for orchestration
# (Docker/K8s probes, load balancers). Deliberately tiny and dependency-free: the endpoint must
# answer without touching any store.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """The public health probe payload."""

    status: str = Field(description="Liveness marker — always 'ok' when the app is serving.")


__all__ = ["HealthStatus"]
