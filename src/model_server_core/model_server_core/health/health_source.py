# ====== Code Summary ======
# HealthSource: the port through which the /health route asks the server what it needs. `ModelServer`
# implements it structurally; the route depends on this contract, not on the server class, so the two
# stay in one direction (server -> health).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol

# ====== Local Project Imports ======
from .health_models import HealthResponse, HealthStatus


class HealthSource(Protocol):
    """What the /health route reads from the server."""

    def is_ready(self) -> bool:
        """Whether the model service is built and can serve requests."""
        ...

    def health_blocker(self) -> str | None:
        """A reason the host can NEVER serve (checked before readiness), or None when it can."""
        ...

    def current_device(self) -> str:
        """The compute device string reported in the body ("cuda" or "cpu")."""
        ...

    def build_health(self, status: HealthStatus, ready: bool, detail: str | None) -> HealthResponse:
        """Build the response body (a server may return a richer subclass)."""
        ...
