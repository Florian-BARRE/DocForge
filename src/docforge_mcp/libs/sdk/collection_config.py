# ====== Code Summary ======
# Collection-config sub-API: state / schema / history (read) + update / rollback (mutations)
# under /api/v1/collections/{collection_id}/config.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class ConfigApi(LoggerClass):
    """Per-collection configuration endpoints (pipeline + metadata schema + version history)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def state(self, collection_id: str) -> Any:
        """Return the collection's complete current config (credentials redacted)."""
        return await self._t.get(f"/collections/{collection_id}/config/state")

    async def schema(self, collection_id: str) -> Any:
        """Return the collection's metadata schema (system + custom fields)."""
        return await self._t.get(f"/collections/{collection_id}/config/schema")

    async def history(self, collection_id: str) -> Any:
        """Return the config version history (newest first)."""
        return await self._t.get(f"/collections/{collection_id}/config/history")

    async def update(
        self, collection_id: str, patch: dict[str, Any], note: str | None = None
    ) -> Any:
        """
        Partially update the config — only the provided keys replace existing values.

        Args:
            collection_id (str): Target collection UUID.
            patch (dict): Partial config document (e.g. a nested ``pipeline`` change).
            note (str | None): Optional change note recorded in the history.

        Returns:
            Any: The new resolved config state (+ transparency envelope).
        """
        return await self._t.post(
            f"/collections/{collection_id}/config/update",
            {"patch": patch, "note": note},
        )

    async def rollback(self, collection_id: str, version: int) -> Any:
        """
        Roll the config back to a previous version (re-applied as a fresh version).

        Args:
            collection_id (str): Target collection UUID.
            version (int): History version number to restore (>= 1).

        Returns:
            Any: The new resolved config state.
        """
        return await self._t.post(
            f"/collections/{collection_id}/config/rollback",
            {"version": version},
        )
