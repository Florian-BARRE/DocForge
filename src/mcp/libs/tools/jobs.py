# ====== Code Summary ======
# MCP tools for the jobs domain — thin wrappers over sdk.jobs (read-only; the rework API has
# no cancel endpoint).

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
    async def list_jobs(collection_id: str) -> Any:
        """List a collection's ingestion jobs, newest first."""
        return await sdk.jobs.list(collection_id)

    @mcp.tool()
    async def get_job(job_id: str) -> Any:
        """Fetch one ingestion job's live state — poll this after an upload."""
        return await sdk.jobs.get(job_id)

    @mcp.tool()
    async def get_job_events(job_id: str) -> Any:
        """Return the job's per-node execution trace, in order (stage, status, timing, error)."""
        return await sdk.jobs.get_events(job_id)

    @mcp.tool()
    async def get_live_workers() -> Any:
        """Return what every worker is doing right now, grouped by worker (empty when idle)."""
        return await sdk.jobs.live_workers()
