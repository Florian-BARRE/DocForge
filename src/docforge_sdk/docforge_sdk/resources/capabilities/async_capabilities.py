# ====== Code Summary ======
# The asynchronous deployment discovery resource: the awaiting shell over the shared
# ``_CapabilitiesSpecs`` builders.

# ====== Local Project Imports ======
from ...models.capabilities import CapabilitiesResponse
from .._base import AsyncResource
from .specs import _CapabilitiesSpecs


class AsyncCapabilities(AsyncResource, _CapabilitiesSpecs):
    """Asynchronous deployment discovery."""

    async def capabilities(self) -> CapabilitiesResponse:
        """
        Discover what this deployment can do right now.

        Returns:
            CapabilitiesResponse: Version, auth state, GPU presence, the service list and the matrix.
        """
        return await self._transport.request_bare(self._describe_spec(), CapabilitiesResponse)
