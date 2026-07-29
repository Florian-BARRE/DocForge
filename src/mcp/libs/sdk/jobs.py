# ====== Code Summary ======
# Jobs sub-API: read-only ingestion status under /api/v1/jobs. The worker writes every job
# row (running, progress per node, done/failed with the error verbatim); this sub-API only
# reads it. There is no cancel endpoint in the rework API.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class JobsApi(LoggerClass):
    """Read-only ingestion job status endpoints."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(self, collection_id: str) -> Any:
        """
        List a collection's jobs, newest first (collection_id is required by the API).

        Args:
            collection_id (str): The collection's UUID.
        """
        return await self._t.get("/jobs", params={"collection_id": collection_id})

    async def live_workers(self) -> Any:
        """Return what every worker is doing right now (derived from RUNNING job rows)."""
        return await self._t.get("/jobs/workers/live")

    async def get_events(self, job_id: str) -> Any:
        """Return the job's per-node execution trace, in order."""
        return await self._t.get(f"/jobs/{job_id}/events")

    async def get(self, job_id: str) -> Any:
        """Return one ingestion job's live state (poll this after an upload)."""
        return await self._t.get(f"/jobs/{job_id}")
