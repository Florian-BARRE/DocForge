# ====== Code Summary ======
# Health sub-API: the public liveness probe (GET /health — outside /api/v1, credential-free
# even when AUTH_ENABLED is true).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class HealthApi(LoggerClass):
    """The health endpoint of the DocForge API."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def ping(self) -> Any:
        """Report process liveness — a static ``{"status": "ok"}`` when the app is serving."""
        return await self._t.get_public("/health")
