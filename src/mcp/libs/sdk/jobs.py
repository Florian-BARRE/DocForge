# ====== Code Summary ======
# Jobs sub-API: global job listing / detail / cancel under /api/v1/jobs.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class JobsApi(LoggerClass):
    """Pipeline job endpoints (track and cancel async ingestion/reindex work)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(
        self,
        status: str | None = None,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        """
        List jobs across all collections (newest first), with optional filters.

        Args:
            status (str | None): Filter by job status.
            collection_id (str | None): Filter by collection UUID.
            limit (int): Page size (1–200).
            offset (int): Page offset.

        Returns:
            Any: Paginated jobs with the total match count.
        """
        return await self._t.get(
            "/jobs",
            params={
                "status": status,
                "collection_id": collection_id,
                "limit": limit,
                "offset": offset,
            },
        )

    async def get(self, job_id: str) -> Any:
        """
        Fetch a single job, enriched with its live arq-side status.

        Args:
            job_id (str): Job UUID.

        Returns:
            Any: The job record with live queue status.
        """
        return await self._t.get(f"/jobs/{job_id}")

    async def cancel(self, job_id: str) -> Any:
        """
        Request cancellation of a queued or running job (arq abort).

        Args:
            job_id (str): Job UUID.

        Returns:
            Any: Whether the abort was accepted.
        """
        return await self._t.post(f"/jobs/{job_id}/cancel")
