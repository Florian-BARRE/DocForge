# ====== Code Summary ======
# MCP tools for the document explorer domain — thin wrappers over sdk.explorer (the read-only
# browse surface: catalogue, facts, pages, IR, chunks, toggles, and the coherent delete).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Annotated, Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, BulkChunkEnabledPatch
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# ====== Local Project Imports ======
from ..compact_json import compact_json
from .reading_rendering import ReadingTextRenderer


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register document explorer tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_documents(
        collection_id: str,
        limit: Annotated[
            int | None, Field(ge=1, description="Max documents to return (server default 500).")
        ] = None,
        offset: Annotated[
            int | None, Field(ge=0, description="Documents to skip (paging).")
        ] = None,
    ) -> Any:
        """
        Return a collection's documents, newest first - the browse catalogue.

        Page with limit/offset on a large collection: exactly `limit` rows back means more may
        exist. To find documents by metadata, use search_collection / browse_chunks filters.
        """
        documents = await sdk.explorer.list_documents(collection_id, limit, offset)
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
        """
        Return the document's full canonical IR - blocks, tables, figures, enrichments. VERY large
        (it can be hundreds of thousands of characters): to read a document prefer
        get_document_outline, then get_document_markdown(pages=...), get_document_chunks or
        get_chunk_context. Use this only to inspect the parse itself.
        """
        ir = await sdk.explorer.get_ir(document_id)
        return ir.model_dump(mode="json")

    @mcp.tool()
    async def get_document_provenance(document_id: str) -> Any:
        """
        Return a document's ingestion provenance - the parser/model pipeline (per-stage trace) that
        produced its IR + chunks. It is large and about HOW the document was processed, not what it
        says: to read content use get_document_outline, get_document_chunks or get_chunk_context.
        """
        provenance = await sdk.explorer.get_provenance(document_id)
        return provenance.model_dump(mode="json")

    @mcp.tool()
    async def get_document_outline(
        document_id: str,
        format: Annotated[
            Literal["text", "json"],
            Field(
                description="'text' (default) = one indented line per heading; 'json' = compact."
            ),
        ] = "text",
    ) -> Any:
        """
        The document's table of contents - the cheap first step to read a long document.

        OUTPUT (format="text"): a title line, then one line per heading, indented by level:
        `<text> | p.<page_number> | chunk <chunk_id>` (page_number is 1-based; chunk is the first
        chunk of that section). Then read the section with get_document_markdown(pages="5-7"),
        or get_chunk_context(chunk_id) / get_document_chunks. format="json": the compact
        {document_id, display_title, page_count, headings[]}.
        """
        outline = await sdk.explorer.get_outline(document_id)
        if format == "json":
            return outline.model_dump(mode="json")
        return ReadingTextRenderer().render_outline(outline)

    @mcp.tool()
    async def get_chunk_context(
        chunk_id: str,
        before: Annotated[int, Field(ge=0, le=5, description="Chunks to include before.")] = 1,
        after: Annotated[int, Field(ge=0, le=5, description="Chunks to include after.")] = 1,
        format: Annotated[
            Literal["text", "json"],
            Field(description="'text' (default) = readable window; 'json' = compact."),
        ] = "text",
    ) -> Any:
        """
        A chunk plus its neighbours in the same document - the #1 way to read around a search hit
        (a hit is often a fragment; its neighbours give the surrounding passage).

        Pass the chunk_id of a search_collection / browse_chunks hit or an outline heading.
        OUTPUT (format="text"): a title line, then per chunk `[index] p.N | heading > path` and its
        text; the requested chunk carries a `*` after its index. Disabled (non-searchable)
        neighbours are skipped, so the window may reach further than before/after. format="json":
        the compact {document_id, display_title, chunks[]} (each with is_target).
        """
        context = await sdk.explorer.get_chunk_context(chunk_id, before, after)
        if format == "json":
            return context.model_dump(mode="json")
        return ReadingTextRenderer().render_context(context)

    @mcp.tool()
    async def get_document_chunks(
        document_id: str,
        limit: Annotated[int, Field(ge=1, le=500, description="Chunks per page.")] = 20,
        offset: Annotated[int, Field(ge=0, description="Chunks to skip (paging).")] = 0,
        include_geometry: Annotated[
            bool, Field(description="true = also return block_ids and the 0-based page.")
        ] = False,
        format: Annotated[
            Literal["text", "json"],
            Field(description="'text' (default) = readable blocks; 'json' = compact."),
        ] = "text",
    ) -> Any:
        """
        A document's retrieval chunks, one page at a time, in reading order.

        Agent defaults: 20 chunks per call and no geometry. The output starts with
        `chunks A-B of TOTAL` - page on with offset (offset += limit) until B == TOTAL. For one
        section prefer get_document_outline then get_chunk_context; for raw page text use
        get_document_markdown(pages=...).

        OUTPUT (format="text"): per chunk `[index] p.<page_number> | heading > path | N tokens |
        chunk <id>` then the text. format="json": compact {total, offset, chunks[]} with the full
        chunk fields (enrichment metadata, role, enabled...).
        """
        page = await sdk.explorer.get_chunks_page(document_id, limit, offset, include_geometry)
        if format == "json":
            chunks = [chunk.model_dump(mode="json", exclude_unset=True) for chunk in page.items]
            return compact_json({"total": page.total, "offset": offset, "chunks": chunks})
        return ReadingTextRenderer().render_chunk_page(page, offset)

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
