# ====== Code Summary ======
# MCP tools for the collections domain — thin wrappers over sdk.collections.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, CreateCollectionRequest, FieldSpec, UpdateCollectionRequest
from docforge_sdk.models import CollectionSnippet, DocumentFilter
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register collection tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_collections() -> Any:
        """List every collection with its full contract (schema, pipeline, search blobs)."""
        collections = await sdk.collections.list()
        return [collection.model_dump(mode="json") for collection in collections]

    @mcp.tool()
    async def get_collection(collection_id: str) -> Any:
        """Return one collection's full contract."""
        collection = await sdk.collections.get(collection_id)
        return collection.model_dump(mode="json")

    @mcp.tool()
    async def create_collection(
        name: str,
        supported_formats: list[str],
        max_file_size_bytes: int,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
    ) -> Any:
        """
        Create a collection from A to Z. `fields` is the FULL metadata schema declared up
        front (each item: field_name, field_type, required, filterable, lexical, semantic,
        enum_values, origin, scope) — the vector space is fixed at creation and cannot grow
        later. `pipeline` is the ingestion graph blob; omit it to use the product default
        (all stages wired).
        """
        request = CreateCollectionRequest(
            name=name,
            supported_formats=supported_formats,
            max_file_size_bytes=max_file_size_bytes,
            # The LLM passes plain dicts at the tool boundary; validate each into the SDK's typed
            # FieldSpec so the request is correctly typed (and malformed fields fail fast here).
            fields=[FieldSpec(**field) for field in fields] if fields else [],
            pipeline=pipeline,
        )
        collection = await sdk.collections.create(request)
        return collection.model_dump(mode="json")

    @mcp.tool()
    async def update_collection(
        collection_id: str,
        name: str | None = None,
        supported_formats: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
        search: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> Any:
        """
        Patch identity/limits, the metadata schema (applied by diff against field_name — an
        omitted field is removed), and/or the config blobs (pipeline / search graphs, each
        validated before storage). A change to the searchable schema flips needs_reindex.
        """
        # 1. Only carry the knobs the caller actually set — an omitted param means "no change",
        #    so it must stay unset on the request rather than serialise as an explicit null.
        provided = {
            key: value
            for key, value in {
                "name": name,
                "supported_formats": supported_formats,
                "max_file_size_bytes": max_file_size_bytes,
                "fields": fields,
                "pipeline": pipeline,
                "search": search,
                "note": note,
            }.items()
            if value is not None
        }
        request = UpdateCollectionRequest.model_validate(provided)
        collection = await sdk.collections.update(collection_id, request)
        return collection.model_dump(mode="json")

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
        it rests on, and human-readable caveats. `total_cost_usd` is null when no stage could be
        priced; `cost_complete` is false when any enabled paid stage had no known rate.
        """
        estimate = await sdk.collections.estimate(
            collection_id,
            scope=scope,
            document_ids=document_ids,
            filter=DocumentFilter(**filter) if filter is not None else None,
        )
        return estimate.model_dump(mode="json")

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
