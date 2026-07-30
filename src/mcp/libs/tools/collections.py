# ====== Code Summary ======
# MCP tools for the collections domain — thin wrappers over sdk.collections.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, CreateCollectionRequest, FieldSpec, UpdateCollectionRequest
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
