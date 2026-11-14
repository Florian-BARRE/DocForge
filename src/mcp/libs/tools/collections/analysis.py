# ====== Code Summary ======
# MCP tools that analyse a collection without changing its content — storage footprint, ingestion
# cost estimate and the dry-run pipeline previews (inline and worker-side). Thin wrappers over
# sdk.collections.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import DocumentFilter
from mcp.server.mcpserver import MCPServer


def register_analysis_tools(mcp: MCPServer, sdk: AsyncClient) -> None:
    """Register the collection analysis tools (footprint, cost estimate, pipeline previews).

    Args:
        mcp (MCPServer): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def collection_storage_footprint(collection_id: str) -> Any:
        """
        Measure a collection's material footprint per store (404 when unknown). S3 bytes are
        EXACT (deduped); Postgres and Qdrant bytes are ESTIMATES (each section flags this via
        its own `estimated`). Includes a per-document breakdown, heaviest first.
        """
        storage = await sdk.collections.storage(collection_id)
        return storage.model_dump(mode="json")

    @mcp.tool()
    async def estimate_collection_cost(
        collection_id: str,
        scope: Literal["pending", "all"] = "pending",
        document_ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
    ) -> Any:
        """
        Project a collection's ingestion cost and volume BEFORE spending (404 when unknown). This
        is an ESTIMATE, not a quote. `scope` picks the whole-collection target — `pending`
        (uploaded-but-not-yet-ingested, the default preview) or `all` (every document). To scope a
        SUBSET instead, pass `document_ids` (a specific selection) OR `filter` (the same shape as the
        documents-grid filter) — either one overrides `scope`; they are mutually exclusive. Returns
        the per-stage token/call/cost breakdown, projected material volume, totals, the assumptions
        it rests on, and human-readable caveats. `total_cost_usd` is null whenever any enabled paid
        stage has no known rate (`cost_complete` false) — then report `total_cost_lower_bound_usd`
        as a minimum ("≥ $X") and relay the caveat naming the unpriced model, its stage and the
        `estimate_overrides.rates` path to price it; never present the lower bound as the total.
        """
        estimate = await sdk.collections.estimate(
            collection_id,
            scope=scope,
            document_ids=document_ids,
            filter=DocumentFilter(**filter) if filter is not None else None,
        )
        return estimate.model_dump(mode="json")

    @mcp.tool()
    async def preview_pipeline(
        collection_id: str,
        document_id: str,
        blob: dict[str, Any] | None = None,
        max_chunks: int | None = None,
    ) -> Any:
        """
        Dry-run the ingestion pipeline on ONE already-ingested document and return a bounded preview —
        NOTHING is persisted (no document, blob or vector is written). Runs the ingest graph inline on
        `document_id` (404 when the collection or document is unknown), optionally with a candidate
        `blob` instead of the collection's stored pipeline. Returns an IR summary, the first N chunks
        (text truncated; cap with `max_chunks`), the run's ACTUAL metered cost, and the full execution
        trace. A node that fails is DATA here (`ok` is false + `failed_node_id` + the partial trace),
        never an error — so this is the way to see what a pipeline change WOULD do before applying it.
        """
        preview = await sdk.collections.preview_pipeline(
            collection_id,
            document_id=document_id,
            blob=blob,
            max_chunks=max_chunks,
        )
        return preview.model_dump(mode="json")

    @mcp.tool()
    async def submit_preview_job(
        collection_id: str,
        document_id: str,
        blob: dict[str, Any] | None = None,
        max_chunks: int | None = None,
    ) -> Any:
        """
        Submit an ASYNCHRONOUS worker-side dry-run preview on one already-ingested document — returns a
        pollable preview id, NOTHING is persisted. Unlike `preview_pipeline` (inline, API-process), the
        worker runs the FULL ingest graph with every dependency present (docling included), so it covers
        ALL pipelines — use it when `preview_pipeline` cannot parse the collection's pipeline. Optionally
        pass a candidate `blob` instead of the stored pipeline. Poll the returned id with
        `get_preview_job` until status is 'done' (the report) or 'failed' (the worker job crashed).
        """
        accepted = await sdk.collections.submit_preview_job(
            collection_id,
            document_id=document_id,
            blob=blob,
            max_chunks=max_chunks,
        )
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def get_preview_job(collection_id: str, preview_id: str) -> Any:
        """
        Poll an asynchronous dry-run preview by its id (from `submit_preview_job`). The bounded report
        appears in `result` once `status` is 'done'; a failed NODE is DATA there (`result.ok` is false),
        while `status` 'failed' is reserved for the worker job itself crashing/timing out. An
        unknown/expired id is a 404 (the result TTL elapsed).
        """
        poll = await sdk.collections.get_preview_job(collection_id, preview_id)
        return poll.model_dump(mode="json")
