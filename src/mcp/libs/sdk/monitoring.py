# ====== Code Summary ======
# Monitoring sub-API: queue / workers / overview / resources / discovery under /api/v1/monitoring.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class MonitoringApi(LoggerClass):
    """Read-only operational snapshots (queue depth, worker fleet, aggregate overview)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def queue(self) -> Any:
        """Return queue depth, per-status job counts, and recent throughput."""
        return await self._t.get("/monitoring/queue")

    async def workers(self) -> Any:
        """Return the live worker fleet with per-worker load/resource gauges."""
        return await self._t.get("/monitoring/workers")

    async def overview(self) -> Any:
        """Return an aggregate snapshot (queue + workers) for a dashboard."""
        return await self._t.get("/monitoring/overview")

    async def resources(self) -> Any:
        """Return the resource snapshot: device gauge + admission limits + live load (Brique D)."""
        return await self._t.get("/monitoring/resources")

    async def discovery(self) -> Any:
        """Return the descriptor that drives the monitoring UI tab."""
        return await self._t.get("/monitoring/discovery")
