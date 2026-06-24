# ====== Code Summary ======
# Per-collection resource-limits sub-API: GET the configured caps + live usage,
# and PUT to replace them. Mirrors the backend's limits router mounted at
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
            Any: CollectionLimitsResponse — caps + in-flight count + budget spent/remaining.
        """
        # 1. GET the limits sub-resource for this collection
        return await self._t.get(f"/collections/{collection_id}/limits")

    async def update(
        self,
        collection_id: str,
        max_in_flight: int | None = None,
        budget_cap_usd: float | None = None,
    ) -> Any:
        """
        Replace the collection's resource limits (PUT semantics — both caps are set).

        Pass ``None`` for a cap to clear it (unlimited).  The server rejects a value of
        ``0`` for either cap because zero would permanently freeze the collection — use
        ``None`` to express "no limit".

        Args:
            collection_id (str): UUID of the target collection.
            max_in_flight (int | None): Per-collection running+pending job cap (null = unlimited).
            budget_cap_usd (float | None): Cumulative spend cap in USD (null = unlimited).

        Returns:
            Any: CollectionLimitsResponse — refreshed caps + live usage.
        """
        # 1. Build the body; include null-valued keys so the server replaces both caps
        body: dict[str, Any] = {
            "max_in_flight": max_in_flight,
            "budget_cap_usd": budget_cap_usd,
        }

        # 2. PUT replaces both caps in one call
        return await self._t.put(f"/collections/{collection_id}/limits", body)
