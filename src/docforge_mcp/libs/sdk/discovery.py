# ====== Code Summary ======
# Discovery sub-API: the self-describing endpoint catalogue (GET /api/v1/discovery).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class DiscoveryApi(LoggerClass):
    """The unified discovery surface (every endpoint's input/output contract + dynamic choices)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def get(self, collection_id: str | None = None) -> Any:
        """
        Describe every endpoint; optionally resolve collection-scoped choices.

        Args:
            collection_id (str | None): When set, resolves search filters/weights and ingest
                metadata choices from that collection's metadata schema.

        Returns:
            Any: The discovery descriptor (endpoints + OpenAPI components).
        """
        return await self._t.get("/discovery", params={"collection_id": collection_id})
