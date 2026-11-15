# ====== Code Summary ======
# The asynchronous liveness probe resource: the awaiting shell over the shared ``_HealthSpecs``
# builders.

# ====== Local Project Imports ======
from ...models.health import HealthStatus
from .._base import AsyncResource
from .specs import _HealthSpecs


class AsyncHealth(AsyncResource, _HealthSpecs):
    """Asynchronous liveness probe."""

    async def ping(self) -> HealthStatus:
        """
        Probe the API's liveness.

        Returns:
            HealthStatus: The status payload (``status == "ok"`` when serving).
        """
        return await self._transport.request_bare(self._ping_spec(), HealthStatus)
