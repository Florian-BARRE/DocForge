# ====== Code Summary ======
# The public entry points: AsyncClient and Client. Each owns a transport and wires every resource
# group onto itself (auth, health, collections, documents, explorer, search, jobs, blobs, pipelines).
# Both support context-manager use so the underlying httpx client is always closed.

# ====== Standard Library Imports ======
from types import TracebackType

# ====== Local Project Imports ======
from ._transport_async import AsyncTransport
from ._transport_sync import SyncTransport
from .resources.audit import AsyncAudit, SyncAudit
from .resources.auth import AsyncAuth, SyncAuth
from .resources.blobs import AsyncBlobs, SyncBlobs
from .resources.collections import AsyncCollections, SyncCollections
from .resources.corpus import AsyncCorpus, SyncCorpus
from .resources.documents import AsyncDocuments, SyncDocuments
from .resources.explorer import AsyncExplorer, SyncExplorer
from .resources.health import AsyncHealth, SyncHealth
from .resources.jobs import AsyncJobs, SyncJobs
from .resources.pipelines import AsyncPipelines, SyncPipelines
from .resources.search import AsyncSearch, SyncSearch
from .resources.snippets import AsyncSnippets, SyncSnippets
from .resources.transfers import AsyncTransfers, SyncTransfers


class AsyncClient:
    """
    Asynchronous DocForge API client.

    Attributes:
        auth (AsyncAuth): API-key management resource.
        health (AsyncHealth): Liveness probe.
        collections (AsyncCollections): Collection CRUD.
        documents (AsyncDocuments): Document admission + searchability control.
        explorer (AsyncExplorer): Document/chunk read surface + IR + toggles.
        search (AsyncSearch): Hybrid search.
        jobs (AsyncJobs): Ingestion-job monitoring.
        blobs (AsyncBlobs): Content-addressed blob fetch.
        pipelines (AsyncPipelines): Pipeline discovery + design.
        transfers (AsyncTransfers): Collection export/import.
        snippets (AsyncSnippets): Granular collection-config snippet export/apply.
        audit (AsyncAudit): Root-only audit-trail reads.
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
        self.audit = AsyncAudit(self._transport)
        self.auth = AsyncAuth(self._transport)
        self.health = AsyncHealth(self._transport)
        self.collections = AsyncCollections(self._transport)
        self.documents = AsyncDocuments(self._transport)
        self.explorer = AsyncExplorer(self._transport)
        self.search = AsyncSearch(self._transport)
        self.jobs = AsyncJobs(self._transport)
        self.blobs = AsyncBlobs(self._transport)
        self.pipelines = AsyncPipelines(self._transport)
        self.transfers = AsyncTransfers(self._transport)
        self.snippets = AsyncSnippets(self._transport)
        self.corpus = AsyncCorpus(self._transport)

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
        health (SyncHealth): Liveness probe.
        collections (SyncCollections): Collection CRUD.
        documents (SyncDocuments): Document admission + searchability control.
        explorer (SyncExplorer): Document/chunk read surface + IR + toggles.
        search (SyncSearch): Hybrid search.
        jobs (SyncJobs): Ingestion-job monitoring.
        blobs (SyncBlobs): Content-addressed blob fetch.
        pipelines (SyncPipelines): Pipeline discovery + design.
        transfers (SyncTransfers): Collection export/import.
        snippets (SyncSnippets): Granular collection-config snippet export/apply.
        audit (SyncAudit): Root-only audit-trail reads.
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
        self.audit = SyncAudit(self._transport)
        self.auth = SyncAuth(self._transport)
        self.health = SyncHealth(self._transport)
        self.collections = SyncCollections(self._transport)
        self.documents = SyncDocuments(self._transport)
        self.explorer = SyncExplorer(self._transport)
        self.search = SyncSearch(self._transport)
        self.jobs = SyncJobs(self._transport)
        self.blobs = SyncBlobs(self._transport)
        self.pipelines = SyncPipelines(self._transport)
        self.transfers = SyncTransfers(self._transport)
        self.snippets = SyncSnippets(self._transport)
        self.corpus = SyncCorpus(self._transport)

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
