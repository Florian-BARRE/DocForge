# ====== Code Summary ======
# MCP tools for the jobs domain — thin wrappers over sdk.jobs (read-only; the rework API has
# no cancel endpoint).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register job tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_jobs(collection_id: str) -> Any:
        """List a collection's ingestion jobs, newest first."""
        jobs = await sdk.jobs.list(collection_id)
        return [job.model_dump(mode="json") for job in jobs]

    @mcp.tool()
    async def get_job(job_id: str) -> Any:
        """Fetch one ingestion job's live state — poll this after an upload."""
        job = await sdk.jobs.get(job_id)
        return job.model_dump(mode="json")

    @mcp.tool()
    async def get_job_events(job_id: str) -> Any:
        """Return the job's per-node execution trace, in order (stage, status, timing, error)."""
        trace = await sdk.jobs.get_events(job_id)
        return trace.model_dump(mode="json")

    @mcp.tool()
    async def get_live_workers() -> Any:
        """Return what every worker is doing right now, grouped by worker (empty when idle)."""
        live = await sdk.jobs.live_workers()
        return live.model_dump(mode="json")
