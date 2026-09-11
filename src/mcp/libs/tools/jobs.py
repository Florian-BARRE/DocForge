# ====== Code Summary ======
# MCP tools for the jobs domain — thin wrappers over sdk.jobs. wait_for_job additionally polls
# sdk.jobs.get in a server-side loop with backoff, so a caller doesn't have to round-trip get_job
# itself after every upload/reingest.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
import time
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP

# A job's status is one of these once it stops changing (see JobStatus.status docstring).
_TERMINAL_JOB_STATUSES = frozenset({"done", "failed", "cancelled"})

# Hard ceiling on wait_for_job's timeout_s — a single tool call must not be able to block the
# server (or a caller's own request timeout) indefinitely. Kept comfortably BELOW a standard MCP
# client's default sse_read_timeout (300s, e.g. mcp.client.streamable_http.streamablehttp_client) —
# this server runs stateless_http=True + json_response=True (see libs/server.py::build_http_app),
# so a call_tool POST blocks for the entire tool duration with no interim event ever reaching the
# client (Context.report_progress's notification is only forwarded to a *streaming* SSE response,
# never to a stateless json_response one — verified against mcp.server.streamable_http's
# _handle_post_request, which drains and discards notifications from request_stream_reader while
# waiting for the final JSONRPCResponse). A cap at or above 300s would let the client's own socket
# read time out and sever the connection before this tool ever gets to return its response, even
# though the server-side poll loop was behaving correctly. 240s leaves ~60s of margin for network
# latency and server-side overhead on top of the poll loop itself.
_MAX_WAIT_TIMEOUT_S = 240.0

# Poll backoff: start fast (a small upload can finish in well under a second), back off to avoid
# hammering the API while a slow ingestion runs.
_POLL_INITIAL_DELAY_S = 0.5
_POLL_MAX_DELAY_S = 5.0
_POLL_BACKOFF_FACTOR = 1.5


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register job tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_jobs(
        collection_id: str | None = None,
        status: list[str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort: str | None = None,
    ) -> Any:
        """List one page of ingestion jobs — a collection's, or (no collection_id) the whole fleet's.

        Omit ``collection_id`` for a FLEET-WIDE listing (full-access token only) — the "All Jobs"
        view. Triage filters (all optional, additive): ``status`` (one or more of pending/running/
        done/failed/cancelled), ``stage`` (the node the job is in), ``error_type`` (structured
        failure class), ``search`` (prefix-match the job OR document id), and the
        ``created_after``/``created_before`` ISO-8601 date range. ``sort`` is the dimension
        (``created`` default, ``duration`` or ``status``) and ``order`` its direction (``newest``
        = DESC default, ``oldest`` = ASC — FIFO/"what runs next", typically with status=["pending"]).
        Each job carries ``duration_seconds`` (its run time). The list is bounded server-side;
        ``total``/``limit``/``offset`` drive pagination and ``jobs`` holds the page.
        """
        page = await sdk.jobs.list(
            collection_id,
            status=status,
            order=order,
            limit=limit,
            offset=offset,
            stage=stage,
            error_type=error_type,
            search=search,
            created_after=created_after,
            created_before=created_before,
            sort=sort,
        )
        return page.model_dump(mode="json")

    @mcp.tool()
    async def get_failure_breakdown(
        collection_id: str | None = None, window_hours: int | None = None
    ) -> Any:
        """Aggregate recent failures — top causes, by stage, by collection — over a look-back window.

        The "why is it breaking" roll-up: FAILED jobs created in the last ``window_hours`` (default
        24, max 720) grouped three ways, each biggest-first and bounded. Omit ``collection_id`` for
        a fleet-wide breakdown (full-access token only).
        """
        breakdown = await sdk.jobs.failure_breakdown(collection_id, window_hours)
        return breakdown.model_dump(mode="json")

    @mcp.tool()
    async def get_new_failures(
        since: str,
        collection_id: str | None = None,
        include_ids: bool | None = None,
        limit: int | None = None,
    ) -> Any:
        """Count jobs that have FAILED since a cursor — the "X new failures since you last looked" signal.

        ``since`` is an ISO-8601 timestamp (your last-seen cursor); only failures finished strictly
        after it count. Returns the count, the newest failure time (pass it as the next ``since``),
        and — when ``include_ids`` is true — the bounded list of new-failure ids. Omit
        ``collection_id`` for a fleet-wide signal (full-access token only).
        """
        result = await sdk.jobs.new_failures(
            since, collection_id=collection_id, include_ids=include_ids, limit=limit
        )
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_job_timeseries(
        collection_id: str | None = None, window_hours: int | None = None
    ) -> Any:
        """Lightweight hourly job trends — created/done/failed per hour plus a reconstructed backlog.

        Contiguous hourly buckets over the last ``window_hours`` (default 24, max 168), computed from
        the job table (no Prometheus). Omit ``collection_id`` for a fleet-wide series (full-access
        token only).
        """
        series = await sdk.jobs.timeseries(collection_id, window_hours)
        return series.model_dump(mode="json")

    @mcp.tool()
    async def get_job(job_id: str) -> Any:
        """Fetch one ingestion job's live state — poll this after an upload."""
        job = await sdk.jobs.get(job_id)
        return job.model_dump(mode="json")

    @mcp.tool()
    async def wait_for_job(job_id: str, timeout_s: float = 120.0) -> Any:
        """
        Block until a job reaches a terminal state (done/failed/cancelled) or timeout_s elapses,
        then return its current JobStatus either way — check the returned `status` field to tell
        the two outcomes apart (a non-terminal status means the timeout was hit; call this again,
        or get_job, to keep watching). Use this right after upload_document,
        upload_document_bytes, reingest_document, or reingest_collection instead of polling
        get_job(job_id) yourself in a loop. `timeout_s` is capped at 240 seconds (4 minutes) — kept
        under a standard MCP client's default 300s read timeout so this call always returns a
        response before such a client's own connection would time out first. For an ingestion that
        takes longer than that, call this repeatedly (each call resumes polling from the job's
        current state; no progress is lost between calls).
        """
        # 1. Clamp the caller's timeout to the hard ceiling — never block the server indefinitely.
        deadline = time.monotonic() + min(timeout_s, _MAX_WAIT_TIMEOUT_S)
        delay = _POLL_INITIAL_DELAY_S

        # 2. Poll with backoff until terminal or the deadline passes. Each sleep is clamped to
        #    whatever's left of the deadline so the loop can never overshoot timeout_s by a whole
        #    extra _POLL_MAX_DELAY_S (up to 5s) — it returns right at the deadline instead.
        while True:
            job = await sdk.jobs.get(job_id)
            remaining = deadline - time.monotonic()
            if job.status in _TERMINAL_JOB_STATUSES or remaining <= 0:
                return job.model_dump(mode="json")
            await asyncio.sleep(min(delay, remaining))
            delay = min(delay * _POLL_BACKOFF_FACTOR, _POLL_MAX_DELAY_S)

    @mcp.tool()
    async def get_job_events(job_id: str) -> Any:
        """Return the job's per-node execution trace, in order (stage, status, timing, error)."""
        trace = await sdk.jobs.get_events(job_id)
        return trace.model_dump(mode="json")

    @mcp.tool()
    async def get_job_event_payload(
        job_id: str, event_id: str, slot: Literal["input", "output"] = "output"
    ) -> Any:
        """
        Fetch one stage-event's FULL raw input or output payload — get_job_events only returns
        the cheap shape summary (field names/types, not values); this returns the actual data,
        and is only populated when the collection was created/updated with trace_verbosity="full"
        (see create_collection). `event_id` comes from one entry of get_job_events' trace.
        """
        payload = await sdk.jobs.get_event_payload(job_id, event_id, slot=slot)
        return payload.model_dump(mode="json")

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

    @mcp.tool()
    async def get_collection_cost(collection_id: str) -> Any:
        """A collection's paid text-gen roll-up — tokens + USD summed over its documents' jobs."""
        return (await sdk.jobs.cost(collection_id)).model_dump(mode="json")

    @mcp.tool()
    async def get_queue_depth(collection_id: str | None = None) -> Any:
        """Backlog counters (pending/running) — fleet-wide (root token) or for one collection."""
        return (await sdk.jobs.queue(collection_id)).model_dump(mode="json")

    @mcp.tool()
    async def get_stage_durations(collection_id: str) -> Any:
        """Average per-stage wall-clock over a collection's done jobs (a running job's ETA basis)."""
        return (await sdk.jobs.stage_durations(collection_id)).model_dump(mode="json")
