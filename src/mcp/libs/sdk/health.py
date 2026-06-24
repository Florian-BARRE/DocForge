# ====== Code Summary ======
# Health sub-API: liveness / version / GPU probe (GET /api/v1/health/ping).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class HealthApi(LoggerClass):
    """Health endpoints of the DocForge API."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def ping(self) -> Any:
        """Return service status, API version, and GPU availability."""
        return await self._t.get("/health/ping")
