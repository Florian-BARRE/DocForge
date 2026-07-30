# ====== Code Summary ======
# The health (liveness) resource. The probe lives at the BARE origin (/health), outside /api/v1, so
# both shells route through the transport's request_bare helper rather than the versioned request.
# All URL logic lives once in the pure _HealthSpecs mixin; the async/sync shells differ only by await.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.health import HealthStatus
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _HealthSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the health endpoint — the single source of URL logic."""

    _HEALTH_PATH = "/health"

    def _ping_spec(self) -> RequestSpec:
        """
        Build the spec for the liveness probe.

        Returns:
            RequestSpec: A GET on the bare-root ``/health`` route (outside ``/api/v1``).
        """
        return RequestSpec("GET", self._HEALTH_PATH)


class AsyncHealth(AsyncResource, _HealthSpecs):
    """Asynchronous liveness probe."""

    async def ping(self) -> HealthStatus:
        """
        Probe the API's liveness.

        Returns:
            HealthStatus: The status payload (``status == "ok"`` when serving).
        """
        return await self._transport.request_bare(self._ping_spec(), HealthStatus)


class SyncHealth(SyncResource, _HealthSpecs):
    """Synchronous liveness probe."""

    def ping(self) -> HealthStatus:
        """
        Probe the API's liveness.

        Returns:
            HealthStatus: The status payload (``status == "ok"`` when serving).
        """
        return self._transport.request_bare(self._ping_spec(), HealthStatus)


__all__ = ["AsyncHealth", "SyncHealth"]
