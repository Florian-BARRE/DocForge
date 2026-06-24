# ====== Code Summary ======
# MCP tools for the search domain — thin wrappers over sdk.search.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register search tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def search_collection(
        collection_id: str,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
        debug: bool = False,
    ) -> Any:
        """
        Hybrid semantic + keyword search over a collection (BGE-M3 dense + sparse BM25, RRF fusion,
        optional query transform and cross-encoder rerank per the collection config).

        - filters: a Qdrant payload filter, e.g.
          {"must": [{"key": "<field>", "match": {"value": "<v>"}}]}. Use get_config_schema to learn
          filterable fields.
        - weights: per-vector fusion overrides, e.g. {"dense-text": 0.7, "sparse-text": 0.3}.
        - debug: include each result's per-vector rank breakdown (why it surfaced).

        Returns ranked chunks with chunk_id, document_id, score, and raw_text.
        """
        return await sdk.search.collection(
            collection_id, query, top_k=top_k, filters=filters, weights=weights, debug=debug
        )

    @mcp.tool()
    async def search_within_document(
        collection_id: str,
        document_id: str,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
        debug: bool = False,
    ) -> Any:
        """
        Same hybrid search as search_collection, but restricted to a single document's chunks.
        Useful to locate a passage inside one known document.
        """
        return await sdk.search.within_document(
            collection_id, document_id, query, top_k=top_k,
            filters=filters, weights=weights, debug=debug,
        )
