# ====== Code Summary ======
# DocForgeClient — the SDK facade. Builds one shared transport and exposes every domain as a
# sub-API attribute (sdk.collections, sdk.documents, sdk.search, ...). This is the single object
# the MCP tool layer depends on. It is a pure HTTP client of the DocForge REST API — it never
# imports the DocForge domain, so it can be reused by any Python consumer (CLI, notebooks, …).

from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .chunks import ChunksApi
from .collection_config import ConfigApi
from .collections import CollectionsApi
from .discovery import DiscoveryApi
from .documents import DocumentsApi
from .files import FilesApi
from .health import HealthApi
from .jobs import JobsApi
from .monitoring import MonitoringApi
from .pages import PagesApi
from .search import SearchApi
from .transport import DocForgeTransport


class DocForgeClient(LoggerClass):
    """
    Typed async client for the DocForge REST API.

    Composes one pooled transport with per-domain sub-APIs. Construct once and reuse across the
    whole process; call :meth:`aclose` on shutdown to release the connection pool.
    """

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        """
        Build the shared transport and wire every sub-API.

        Args:
            base_url (str): DocForge base URL (e.g. ``http://docforge:8000``).
            timeout (float): Per-request timeout in seconds.
        """
        LoggerClass.__init__(self)
        # 1. One pooled transport shared by every sub-API
        self._transport = DocForgeTransport(base_url, timeout)

        # 2. Compose the domain sub-APIs as attributes
        self.health = HealthApi(self._transport)
        self.discovery = DiscoveryApi(self._transport)
        self.collections = CollectionsApi(self._transport)
        self.config = ConfigApi(self._transport)
        self.documents = DocumentsApi(self._transport)
        self.search = SearchApi(self._transport)
        self.files = FilesApi(self._transport)
        self.chunks = ChunksApi(self._transport)
        self.pages = PagesApi(self._transport)
        self.jobs = JobsApi(self._transport)
        self.monitoring = MonitoringApi(self._transport)

        self.logger.info(f"DocForgeClient ready ({base_url})")

    async def aclose(self) -> None:
        """Release the shared transport's connection pool."""
        await self._transport.aclose()
