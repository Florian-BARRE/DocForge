# ====== Code Summary ======
# MCP tools for the collections domain — thin wrappers over sdk.collections.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, CreateCollectionRequest, FieldSpec, UpdateCollectionRequest
from docforge_sdk.models import BulkReingestRequest, CollectionSnippet, DocumentFilter
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from .schema_diff_rendering import CONFIRM_HINT, SchemaDiffRenderer

# Heavy server-shaped graph blobs dropped from the default (lean) collection view.
_PIPELINE_BLOB_KEYS = ("pipeline", "search")


def _lean(collection: dict[str, Any], include_pipelines: bool) -> dict[str, Any]:
    """
    Project a dumped collection to its lean shape unless the caller opted into the pipeline blobs.

    Args:
        collection (dict[str, Any]): A JSON-dumped CollectionModel / CollectionListItem.
        include_pipelines (bool): Keep the `pipeline` and `search` blobs when True.

    Returns:
        dict[str, Any]: The collection, without the heavy blobs by default.
    """
    if include_pipelines:
        return collection
    return {key: value for key, value in collection.items() if key not in _PIPELINE_BLOB_KEYS}


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register collection tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_collections(include_pipelines: bool = False) -> Any:
        """
        List every collection: identity, limits, health and metadata schema (field descriptions
        included). The heavy `pipeline` / `search` graph blobs are omitted by default; pass
        include_pipelines=true only when you need to inspect or edit them. To learn HOW to search
        a collection (fields, example values, filter grammar), call describe_collection.
        """
        collections = await sdk.collections.list()
        return [
            _lean(collection.model_dump(mode="json"), include_pipelines)
            for collection in collections
        ]

    @mcp.tool()
    async def get_collection(collection_id: str, include_pipelines: bool = False) -> Any:
        """
        Return one collection's contract: identity, limits, title_field and metadata schema (field
        descriptions included). The heavy `pipeline` / `search` graph blobs (tens of thousands of
        characters) are omitted by default; pass include_pipelines=true only when you need to
        inspect or edit them. To learn HOW to search it (fields, example values, filter grammar,
        ready-to-use requests), call describe_collection instead.
        """
        collection = await sdk.collections.get(collection_id)
        return _lean(collection.model_dump(mode="json"), include_pipelines)

    @mcp.tool()
    async def describe_collection(collection_id: str) -> Any:
        """
        Call this FIRST before searching a collection: lists fields (meaning, type, real example
        values), valid search_in targets, the filter grammar and ready-to-use example requests.
        Never includes pipeline/search config or secrets.
        """
        description = await sdk.collections.describe(collection_id)
        return description.model_dump(mode="json")

    @mcp.tool()
    async def create_collection(
        name: str,
        supported_formats: list[str],
        max_file_size_bytes: int,
        tags: list[str] | None = None,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
        preset: Literal["standard", "light", "ocr_scan", "high_precision"] | None = None,
        search_preset: Literal["hybrid", "hybrid_rerank", "dense_only"] | None = None,
        job_timeout_seconds: float | None = None,
        trace_verbosity: Literal["shape", "full"] | None = None,
        title_field: str | None = None,
    ) -> Any:
        """
        Create a collection from A to Z. BEFORE calling this, call
        get_collection_contract_schema() to learn the exact enum values for `supported_formats`
        (`supported_format_tokens`) and for each field's `field_type`/`origin`/`scope`
        (`field_schema`) — do not guess them. To discover the available business presets (label +
        rationale for each), call get_pipeline_design("ingest") / get_pipeline_design("search")
        and read their `presets` list.

        `fields` is the FULL metadata schema declared up front (each item: field_name,
        field_type, required, filterable, lexical, semantic, enum_values, origin, scope, and an
        optional `description` saying what the field means — it is shown to searching agents) — the
        vector space is fixed at creation and cannot grow later; omit for a schema-free
        collection. `pipeline` is the ingestion graph blob (opaque dict); omit it AND leave
        `preset` unset to get the product default ('standard' — all stages wired, thorough but
        slower/costlier). Ingestion presets (ignored if `pipeline` is also set): `preset="light"`
        is the fast on-ramp (enrichment-free core, no config); `preset="ocr_scan"` adds a local OCR
        pass for scanned/image documents; `preset="high_precision"` uses finer chunks for sharper
        retrieval. `search_preset` selects the collection's SEARCH blob: 'hybrid' (default
        dense+sparse fusion), 'hybrid_rerank' (hybrid + cross-encoder rerank) or 'dense_only' (pure
        semantic). `tags` is an optional list of free-form labels for grouping/filtering collections
        in the UI (omit for untagged). `job_timeout_seconds` overrides the worker's default
        whole-ingest-job wall-clock timeout for this collection (omit to inherit the server
        default). `trace_verbosity="full"` additionally stores each pipeline node's raw input/output
        payload (fetchable via get_job_event_payload) instead of just its cheap shape summary —
        costs object-store space, use only while debugging a collection's ingestion.
        `title_field` names a document-scope field whose value becomes each document's display
        title (hit `document_title`); omit to keep the parser-derived title.
        """
        request = CreateCollectionRequest(
            name=name,
            supported_formats=supported_formats,
            tags=tags,
            max_file_size_bytes=max_file_size_bytes,
            # The LLM passes plain dicts at the tool boundary; validate each into the SDK's typed
            # FieldSpec so the request is correctly typed (and malformed fields fail fast here).
            fields=[FieldSpec(**field) for field in fields] if fields else [],
            pipeline=pipeline,
            preset=preset,
            search_preset=search_preset,
            job_timeout_seconds=job_timeout_seconds,
            title_field=title_field,
            # trace_verbosity has no None-means-default meaning on the request model itself
            # (it's a plain "shape"/"full" Literal with default "shape") — an omitted tool
            # argument must fall through to that default rather than being sent as an explicit None.
            **({"trace_verbosity": trace_verbosity} if trace_verbosity is not None else {}),
        )
        collection = await sdk.collections.create(request)
        # Lean like get_collection: the caller supplied the blobs (or a preset) and can read them
        # back with get_collection(include_pipelines=true) — echoing them here only costs tokens.
        return _lean(collection.model_dump(mode="json"), include_pipelines=False)

    @mcp.tool()
    async def update_collection(
        collection_id: str,
        name: str | None = None,
        supported_formats: list[str] | None = None,
        tags: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        field_ops: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
        search: dict[str, Any] | None = None,
        note: str | None = None,
        title_field: str | None = None,
        clear_title_field: bool = False,
        confirm: bool = False,
        preview: bool = False,
    ) -> Any:
        """
        Patch identity/limits, the metadata schema, and/or the config blobs (pipeline / search
        graphs, each validated before storage).
        Schema edits are explicit `field_ops`, applied in order:
        {"op":"add","field":{field_name, field_type, filterable?, semantic?, lexical?, scope?,
        description?...}} · {"op":"update","field_name":..,"changes":{<attrs to change>}} ·
        {"op":"remove","field_name":..} (DELETES the field's stored values) ·
        {"op":"rename","field_name":..,"new_name":..} (keeps the values; title_field follows).
        A remove or rename is only applied with `confirm=true` — without it this returns a
        dry-run `schema_diff` preview (values lost per removed field) and changes nothing.
        `preview=true` previews any patch without writing. `tags` replaces the labels wholesale.
        `title_field` sets the document-scope display-title field; `clear_title_field=true`
        reverts to the parsed title. The result carries the applied `schema_diff`.
        """
        # 1. Only carry the knobs the caller actually set — an omitted param means "no change",
        #    so it must stay unset on the request rather than serialise as an explicit null.
        provided: dict[str, Any] = {
            key: value
            for key, value in {
                "name": name,
                "supported_formats": supported_formats,
                "tags": tags,
                "max_file_size_bytes": max_file_size_bytes,
                "field_ops": field_ops,
                "pipeline": pipeline,
                "search": search,
                "note": note,
            }.items()
            if value is not None
        }
        # title_field has a third state (explicit null = clear) that None-as-omitted cannot express.
        if clear_title_field:
            provided["title_field"] = None
        elif title_field is not None:
            provided["title_field"] = title_field
        # 2. A destructive schema op (remove/rename) without confirm=true is downgraded to a
        #    dry run: the caller sees exactly what would be lost before anything is written.
        gated = SchemaDiffRenderer.needs_confirm(field_ops) and not confirm
        if preview or gated:
            provided["dry_run"] = True
        request = UpdateCollectionRequest.model_validate(provided)
        result = await sdk.collections.update(collection_id, request)
        diff = SchemaDiffRenderer.render(result.schema_diff)
        if result.dry_run:
            hint = CONFIRM_HINT if gated else "preview only — nothing was written"
            return {"applied": False, "schema_diff": diff, "message": hint}
        # 3. Echo the blobs back only when this call edited one (the caller wants to see what was
        #    stored); a schema/identity edit stays lean like get_collection.
        edited_blob = pipeline is not None or search is not None
        dumped = result.model_dump(mode="json", exclude={"schema_diff", "dry_run"})
        return {**_lean(dumped, include_pipelines=edited_blob), "schema_diff": diff}

    @mcp.tool()
    async def delete_collection(collection_id: str) -> Any:
        """Delete a collection (404 when unknown). Irreversible."""
        await sdk.collections.delete(collection_id)
        return {}

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
        collection_id: str, document_ids: list[str] | None = None, force: bool = False
    ) -> Any:
        """
        Re-run the full pipeline over a collection's corpus — every document, or an explicit
        `document_ids` subset (404 when the collection is unknown; 422 on a stale/broken pipeline
        or a bad subset). Idempotent per document; original bytes are already stored, so this never
        re-uploads. `force` bypasses the stage cache and recomputes every stage from scratch. A
        match above the server's fan-out ceiling enqueues only the first N and reports
        `capped=true` with the full `matched` count — poll each returned job handle for progress.
        Documents that already have a running job are skipped (`skipped_in_flight`), not re-queued.
        """
        request = BulkReingestRequest(document_ids=document_ids, force=force)
        accepted = await sdk.collections.reingest(collection_id, request)
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
