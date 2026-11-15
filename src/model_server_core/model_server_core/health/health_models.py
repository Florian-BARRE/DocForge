# ====== Code Summary ======
# HealthStatus and HealthResponse: the shared body of GET /health. The shape (status, ready, detail,
# device) is the one every model host already returns, and the one the DocForge worker's
# EndpointReachability preflight and the app's GET /capabilities probe read. A server that reports more
# (bge adds the model ids) subclasses HealthResponse and overrides `ModelServer.build_health`.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import Enum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Closed set of `status` values of GET /health."""

    OK = "ok"
    LOADING = "loading"
    UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
    """Response model of the GET /health liveness + readiness probe.

    `status` and `device` stay plain strings on the wire (the enumerations above give their values),
    so the OpenAPI document of a server does not change shape.

    Attributes:
        status (str): "ok" when ready, "loading" during startup, "unhealthy" when unserviceable.
        ready (bool): True only when the host can serve inference.
        detail (str | None): Reason the service is not ready (diagnostics only); None on "ok".
        device (str): Runtime compute device: "cuda" when a GPU is present, else "cpu".
    """

    status: str = Field(
        ...,
        description="'ok' when ready, 'loading' during startup, 'unhealthy' when unserviceable.",
    )
    ready: bool = Field(..., description="True when the host can serve inference.")
    detail: str | None = Field(
        default=None, description="Reason the service is not ready; None when status is 'ok'."
    )
    device: str = Field(
        ..., description="Runtime compute device: 'cuda' when a GPU is present, else 'cpu'."
    )
