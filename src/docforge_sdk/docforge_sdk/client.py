# ====== Code Summary ======
# The public entry points: AsyncClient and Client. Each owns a transport and wires the resource groups
# onto itself (only ``auth`` in this slice — later slices add more attributes the same way). Both
# support context-manager use so the underlying httpx client is always closed.

# ====== Standard Library Imports ======
from types import TracebackType

# ====== Local Project Imports ======
from ._transport_async import AsyncTransport
from ._transport_sync import SyncTransport
from .resources.auth import AsyncAuth, SyncAuth


class AsyncClient:
    """
    Asynchronous DocForge API client.

    Attributes:
        auth (AsyncAuth): API-key management resource.
    """

    def __init__(self, base_url: str, timeout: float = 30.0, api_token: str = "") -> None:
        """
        Create the client and wire its resource groups onto the shared transport.

        Args:
            base_url (str): The API origin, e.g. ``"http://localhost:10040"``.
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token; empty means unauthenticated requests.
        """
        self._transport = AsyncTransport(base_url, timeout, api_token)
        self.auth = AsyncAuth(self._transport)

    async def __aenter__(self) -> "AsyncClient":
        """Enter the async context, returning the client itself."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client on context exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying transport and release its connections."""
        await self._transport.aclose()


class Client:
    """
    Synchronous DocForge API client.

    Attributes:
        auth (SyncAuth): API-key management resource.
    """

    def __init__(self, base_url: str, timeout: float = 30.0, api_token: str = "") -> None:
        """
        Create the client and wire its resource groups onto the shared transport.

        Args:
            base_url (str): The API origin, e.g. ``"http://localhost:10040"``.
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token; empty means unauthenticated requests.
        """
        self._transport = SyncTransport(base_url, timeout, api_token)
        self.auth = SyncAuth(self._transport)

    def __enter__(self) -> "Client":
        """Enter the context, returning the client itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client on context exit."""
        self.close()

    def close(self) -> None:
        """Close the underlying transport and release its connections."""
        self._transport.close()


__all__ = ["AsyncClient", "Client"]
