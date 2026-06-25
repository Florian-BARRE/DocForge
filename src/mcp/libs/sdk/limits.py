# ====== Code Summary ======
# Per-collection resource-limits sub-API: GET the configured cap + live usage,
# and PUT to replace it. Mirrors the backend's limits router mounted at
# /api/v1/collections/{collection_id}/limits.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class LimitsApi(LoggerClass):
    """
    Per-collection resource-limits sub-resource (Brique D).

    Exposes the two synchronous endpoints on
    ``/api/v1/collections/{collection_id}/limits``.
    """

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def get(self, collection_id: str) -> Any:
        """
        Return the collection's configured resource limits and live usage.

        Args:
            collection_id (str): UUID of the target collection.

        Returns:
            Any: CollectionLimitsResponse — max_in_flight cap + current in_flight count.
        """
        # 1. GET the limits sub-resource for this collection
        return await self._t.get(f"/collections/{collection_id}/limits")

    async def update(
        self,
        collection_id: str,
        max_in_flight: int | None = None,
    ) -> Any:
        """
        Replace the collection's in-flight cap (PUT semantics — the cap is set explicitly).

        Pass ``None`` to clear the cap (unlimited).  The server rejects a value of ``0``
        because zero would permanently freeze the collection — use ``None`` instead.

        Args:
            collection_id (str): UUID of the target collection.
            max_in_flight (int | None): Per-collection running+pending job cap (null = unlimited).

        Returns:
            Any: CollectionLimitsResponse — refreshed max_in_flight cap + live in_flight count.
        """
        # 1. Build the body; null is sent explicitly so the server clears the cap
        body: dict[str, Any] = {
            "max_in_flight": max_in_flight,
        }

        # 2. PUT replaces the cap in one call
        return await self._t.put(f"/collections/{collection_id}/limits", body)
