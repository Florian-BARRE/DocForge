# ====== Code Summary ======
# MCP tools for the document explorer domain — thin wrappers over sdk.explorer (the read-only
# browse surface: catalogue, facts, pages, IR, chunks, toggles, and the coherent delete).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, BulkChunkEnabledPatch
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register document explorer tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_documents(collection_id: str) -> Any:
        """Return a collection's documents, newest first — the browse catalogue."""
        documents = await sdk.explorer.list_documents(collection_id)
        return [document.model_dump(mode="json") for document in documents]

    @mcp.tool()
    async def get_document(document_id: str) -> Any:
        """Return one document's full facts and resolved document-level metadata."""
        document = await sdk.explorer.get_document(document_id)
        return document.model_dump(mode="json")

    @mcp.tool()
    async def get_document_pages(document_id: str) -> Any:
        """Return a document's pages, in order — geometry, routing and the render blob reference."""
        pages = await sdk.explorer.get_pages(document_id)
        return [page.model_dump(mode="json") for page in pages]

    @mcp.tool()
    async def get_document_ir(document_id: str) -> Any:
        """Return the document's full canonical IR — blocks, tables, figures, enrichments (can be large)."""
        ir = await sdk.explorer.get_ir(document_id)
        return ir.model_dump(mode="json")

    @mcp.tool()
    async def get_document_provenance(document_id: str) -> Any:
        """Return a document's ingestion provenance — the parser/model pipeline (per-stage trace) that produced its IR + chunks."""
        provenance = await sdk.explorer.get_provenance(document_id)
        return provenance.model_dump(mode="json")

    @mcp.tool()
    async def get_document_chunks(document_id: str) -> Any:
        """Return a document's retrieval chunks — enriched text, composition and generated metadata."""
        chunks = await sdk.explorer.get_chunks(document_id)
        return [chunk.model_dump(mode="json") for chunk in chunks]

    @mcp.tool()
    async def delete_document(document_id: str) -> Any:
        """Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge). Irreversible."""
        await sdk.explorer.delete_document(document_id)
        return {}

    @mcp.tool()
    async def set_chunk_enabled(chunk_id: str, enabled: bool) -> Any:
        """Toggle one chunk's searchability (reversible, no re-embed)."""
        result = await sdk.explorer.set_chunk_enabled(chunk_id, enabled)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def set_chunks_enabled(chunk_ids: list[str], enabled: bool) -> Any:
        """Toggle several chunks' searchability to the same state in one call (multi-select)."""
        patch = BulkChunkEnabledPatch(chunk_ids=chunk_ids, enabled=enabled)
        result = await sdk.explorer.set_chunks_enabled(patch)
        return result.model_dump(mode="json")
