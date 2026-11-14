# ====== Code Summary ======
# MCP tools that maintain a collection's config and index — snippet export/apply, the contract
# schema, health probe, reingest, index rebuild and trace-payload purge. Thin wrappers over
# sdk.collections and sdk.snippets.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import BulkReingestRequest, CollectionSnippet
from mcp.server.mcpserver import MCPServer


def register_maintenance_tools(mcp: MCPServer, sdk: AsyncClient) -> None:
    """Register the collection maintenance tools (snippets, contract schema, health, reingest, index rebuild, trace purge).

    Args:
        mcp (MCPServer): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def export_collection_snippet(
        collection_id: str, kind: Literal["pipeline", "search", "schema"]
    ) -> Any:
        """
        Export one granular config facet as a portable, secret-masked `.dfsnippet` (config-only,
        synchronous — contrast the async whole-collection `.dcexport`). `kind` selects the slice:
        `pipeline` (the ingestion graph), `search` (the search graph), or `schema` (the metadata
        fields). Returns the versioned snippet (kind, format_version, docforge_version, body).
        """
        snippet = await sdk.snippets.export(collection_id, kind)
        return snippet.model_dump(mode="json")

    @mcp.tool()
    async def apply_collection_snippet(
        collection_id: str,
        kind: Literal["pipeline", "search", "schema"],
        snippet: dict[str, Any],
    ) -> Any:
        """
        Apply a `.dfsnippet` of the given `kind` onto an EXISTING collection (healed/validated like a
        PATCH; 422 on a version/kind mismatch or an invalid graph/schema). `snippet` is the wrapper
        returned by export_collection_snippet. Provider secrets from a DIFFERENT collection arrive
        masked and must be re-entered before the graph can run. Returns {collection_id, kind,
        needs_reindex}.
        """
        result = await sdk.snippets.apply(collection_id, kind, CollectionSnippet(**snippet))
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_collection_contract_schema() -> Any:
        """The JSON Schema of the collection identity/limits contract (build a valid create/update)."""
        return (await sdk.collections.contract_schema()).model_dump(mode="json")

    @mcp.tool()
    async def collection_health(collection_id: str) -> Any:
        """
        Probe a collection's operational health on demand — a zero-spend provider reachability
        sweep across the ingest AND search graphs, plus index/doc stats and a rolled-up verdict
        (404 when unknown). No job is enqueued and nothing is billed; this is read-only diagnostics.
        """
        health = await sdk.collections.health(collection_id)
        return health.model_dump(mode="json")

    @mcp.tool()
    async def reingest_collection(
        collection_id: str,
        document_ids: list[str] | None = None,
        force: bool = False,
        replay_from: str | None = None,
        confirm_estimate: bool = False,
    ) -> Any:
        """
        Re-run the full pipeline over a collection's corpus — every document, or an explicit
        `document_ids` subset (404 when the collection is unknown; 422 on a stale/broken pipeline
        or a bad subset). Idempotent per document; original bytes are already stored, so this never
        re-uploads. `force` bypasses the stage cache and recomputes every stage from scratch. A
        match above the server's fan-out ceiling enqueues only the first N and reports
        `capped=true` with the full `matched` count — poll each returned job handle for progress.
        Documents that already have a running job are skipped (`skipped_in_flight`), not re-queued.
        `replay_from` re-runs only that stage and its downstream on the document's PERSISTED IR (no
        re-parse, no re-upload) — one of enrich, chunk, metagen_chunk, metagen_document, embed (e.g.
        `metagen_document` after editing a metagen prompt, `embed` after switching embedder); a stage
        the pipeline cannot replay is a 422 `replay_unsupported` whose `allowed` lists the valid ones. Documents with no persisted IR are skipped (`skipped_not_replayable`).
        A LARGE reingest (more documents than the server's confirm threshold) is refused 409
        `estimate_required`: the error detail carries `matched`, `threshold` and an `estimate`
        summary (total_cost_usd, tokens, priced_stages, caveats). Show/review that cost, then call
        this tool AGAIN with the same arguments plus `confirm_estimate=true` to proceed. A 429
        `queue_saturated` (with Retry-After) means the ingestion queue is full — wait that many
        seconds and retry; nothing was enqueued.
        """
        request = BulkReingestRequest(
            document_ids=document_ids,
            force=force,
            replay_from=replay_from,
            confirm_estimate=confirm_estimate,
        )
        accepted = await sdk.collections.reingest(collection_id, request)
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def rebuild_collection_index(collection_id: str) -> Any:
        """
        Rebuild a collection's vector index from its CURRENT schema, without re-embedding content.
        Use it when search returns a 422 naming a field with no indexed semantic/lexical vector, or
        reingest_collection returns 409 `rebuild_index_required` (a field was made semantic/lexical
        after first ingest — Qdrant cannot add a named vector to a live store). Returns `job_id`
        (202): follow it with wait_for_job — the job's `document_id` is null. Uploads and reingests
        get 409 `rebuild_index_active` while it runs; 409 `collection_busy` when other jobs are live.
        """
        accepted = await sdk.collections.rebuild_index(collection_id)
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def purge_collection_trace_payloads(collection_id: str) -> Any:
        """
        Reclaim every stored full execution-trace payload of a collection's jobs — the heavy
        per-node raw input/output bytes the opt-in `trace_verbosity='full'` tier accumulates in the
        object store. Idempotent: a collection that stored nothing returns zeros (not an error);
        404 only when the collection itself is unknown. Best-effort — the call always succeeds and
        reports `purged_jobs` (jobs considered) + `deleted_objects` (object-store objects removed).
        """
        result = await sdk.collections.purge_trace_payloads(collection_id)
        return result.model_dump(mode="json")
