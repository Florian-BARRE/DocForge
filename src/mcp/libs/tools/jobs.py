# ====== Code Summary ======
# MCP tools for the jobs domain — thin wrappers over sdk.jobs.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register job tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_jobs(
        status: str | None = None,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        """List pipeline jobs across all collections (newest first). Filter by status or collection_id."""
        return await sdk.jobs.list(
            status=status, collection_id=collection_id, limit=limit, offset=offset
        )

    @mcp.tool()
    async def get_job(job_id: str) -> Any:
        """Fetch a single job with its live queue status — use to track an ingestion to completion."""
        return await sdk.jobs.get(job_id)

    @mcp.tool()
    async def cancel_job(job_id: str) -> Any:
        """Request cancellation of a queued or running job (stops at the next await point)."""
        return await sdk.jobs.cancel(job_id)
