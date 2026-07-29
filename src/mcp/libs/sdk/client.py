# ====== Code Summary ======
# DocForgeClient — the SDK facade. Builds one shared transport and exposes every domain as a
# sub-API attribute (sdk.collections, sdk.documents, sdk.search, ...). This is the single object
# the MCP tool layer depends on. It is a pure HTTP client of the DocForge REST API — it never
# imports the DocForge domain, so it can be reused by any Python consumer (CLI, notebooks, …).

from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .auth import AuthApi
from .blobs import BlobsApi
from .collections import CollectionsApi
from .documents import DocumentsApi
from .explorer import ExplorerApi
from .health import HealthApi
from .jobs import JobsApi
from .pipelines import PipelinesApi
from .search import SearchApi
from .transport import DocForgeTransport


class DocForgeClient(LoggerClass):
    """
    Typed async client for the DocForge REST API.

    Composes one pooled transport with per-domain sub-APIs. Construct once and reuse across the
    whole process; call :meth:`aclose` on shutdown to release the connection pool.
    """

    def __init__(self, base_url: str, timeout: float = 60.0, api_token: str = "") -> None:
        """
        Build the shared transport and wire every sub-API.

        Args:
            base_url (str): DocForge base URL (e.g. ``http://docforge:8000``).
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token for the DocForge REST API. When non-empty,
                every outbound HTTP request carries ``Authorization: Bearer <token>``.
                Leave empty when targeting a DocForge instance with ``AUTH_ENABLED=false``.
        """
        LoggerClass.__init__(self)
        # 1. One pooled transport shared by every sub-API — auth token threaded through
        self._transport = DocForgeTransport(base_url, timeout, api_token=api_token)

        # 2. Compose the domain sub-APIs as attributes
        self.health = HealthApi(self._transport)
        self.auth = AuthApi(self._transport)
        self.collections = CollectionsApi(self._transport)
        self.documents = DocumentsApi(self._transport)
        self.explorer = ExplorerApi(self._transport)
        self.search = SearchApi(self._transport)
        self.jobs = JobsApi(self._transport)
        self.blobs = BlobsApi(self._transport)
        self.pipelines = PipelinesApi(self._transport)

        self.logger.info(f"DocForgeClient ready ({base_url})")

    async def aclose(self) -> None:
        """Release the shared transport's connection pool."""
        await self._transport.aclose()
