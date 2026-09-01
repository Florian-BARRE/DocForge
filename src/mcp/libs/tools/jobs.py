# ====== Code Summary ======
# MCP tools for the jobs domain — thin wrappers over sdk.jobs.

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
    async def list_jobs(
        collection_id: str, limit: int | None = None, offset: int | None = None
    ) -> Any:
        """List one page of a collection's ingestion jobs, newest first.

        The list is bounded server-side; ``total``/``limit``/``offset`` drive pagination and
        ``jobs`` holds the page. Pass ``limit``/``offset`` to page a heavily re-ingested collection.
        """
        page = await sdk.jobs.list(collection_id, limit=limit, offset=offset)
        return page.model_dump(mode="json")

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

    @mcp.tool()
    async def cancel_job(job_id: str, force: bool = False) -> Any:
        """
        Stop an ingestion job. By default (force=False) a running job is asked to stop
        cooperatively at its next stage boundary (stays 'running' with cancel_requested=true
        until it does); a queued job is cancelled immediately either way. Pass force=True to
        immediately terminate a running or wedged job regardless of worker state. 409 if the
        job is already terminal (done/failed/cancelled).
        """
        result = await sdk.jobs.cancel(job_id, force=force)
        return result.model_dump(mode="json")
