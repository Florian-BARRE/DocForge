# ====== Code Summary ======
# MCP tools for the pages domain — thin wrappers over sdk.pages. The screenshot tool returns an
# MCP Image (PNG) rather than raw bytes so clients can render it inline.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP, Image

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register page tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_pages(collection_id: str, document_id: str) -> Any:
        """List a document's pages with per-page block/figure/table/chunk counts."""
        return await sdk.pages.list(collection_id, document_id)

    @mcp.tool()
    async def get_page(collection_id: str, document_id: str, page_number: int) -> Any:
        """Full info for one page (0-indexed): its blocks, concatenated text, and covering chunk ids."""
        return await sdk.pages.get(collection_id, document_id, page_number)

    @mcp.tool()
    async def get_page_screenshot(collection_id: str, document_id: str, page_number: int) -> Image:
        """Render a page (0-indexed) as a PNG image, on-the-fly from the original PDF."""
        png_bytes = await sdk.pages.screenshot(collection_id, document_id, page_number)
        return Image(data=png_bytes, format="png")

    @mcp.tool()
    async def reingest_page(collection_id: str, document_id: str, page_number: int) -> Any:
        """Re-run the pipeline for a page — re-runs the whole document (pages are a derived view)."""
        return await sdk.pages.reingest(collection_id, document_id, page_number)
