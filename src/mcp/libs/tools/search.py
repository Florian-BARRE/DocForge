# ====== Code Summary ======
# MCP tools for the search domain — thin wrapper over sdk.search (a single collection-scoped
# retrieval route; there is no per-document search in the rework API).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, SearchRequest, SearchTarget
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register search tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def search_collection(
        collection_id: str,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        search_in: list[dict[str, Any]] | None = None,
        use_late_interaction: bool | None = None,
        rescore_pool_size: int | None = None,
    ) -> Any:
        """
        Hybrid semantic + keyword search over a collection (dense + sparse fusion, optional
        ColBERT late-interaction re-score).

        - filters: exact/any-of constraints on the collection's FILTERABLE fields
          (field -> value, or field -> [values] for any-of). Use get_collection to learn which
          fields are filterable.
        - search_in: targets [{"field": "content" | <metadata field>, "semantic": bool,
          "lexical": bool}]; omit to search the chunk body ("content") on both semantic and
          lexical axes.
        - use_late_interaction: opt into the ColBERT re-score for this query (degrades
          gracefully to standard hybrid if the collection carries no ColBERT vectors).

        Returns ranked hits: chunk_id, document_id, score, text, chunk_index, token_count.
        """
        request = SearchRequest(
            query=query,
            limit=limit,
            filters=filters,
            # The LLM passes plain target dicts; validate each into the SDK's typed SearchTarget.
            search_in=[SearchTarget(**target) for target in search_in] if search_in else None,
            use_late_interaction=use_late_interaction,
            rescore_pool_size=rescore_pool_size,
        )
        result = await sdk.search.search(collection_id, request)
        return result.model_dump(mode="json")
