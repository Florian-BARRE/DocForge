# ====== Code Summary ======
# MCP tools for the search domain — thin wrapper over sdk.search (a single collection-scoped
# retrieval route; there is no per-document search in the DocForge API).

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
    ) -> Any:
        """
        Hybrid semantic + keyword search over a collection (dense + sparse fusion).

        - filters: exact/any-of constraints on the collection's FILTERABLE fields
          (field -> value, or field -> [values] for any-of). Use get_collection to learn which
          fields are filterable.
        - search_in: targets [{"field": "content" | <metadata field>, "semantic": bool,
          "lexical": bool}]; omit to search the chunk body ("content") on both semantic and
          lexical axes.

        Returns ranked hits: chunk_id, document_id, score, text, chunk_index, token_count.
        """
        request = SearchRequest(
            query=query,
            limit=limit,
            filters=filters,
            # The LLM passes plain target dicts; validate each into the SDK's typed SearchTarget.
            search_in=[SearchTarget(**target) for target in search_in] if search_in else None,
        )
        result = await sdk.search.search(collection_id, request)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_search_health() -> Any:
        """
        Deployment-wide search-runtime health summary (cumulative since process start).

        Search runs inline (no job/fleet surface), so this is the operational snapshot: total_runs,
        error_rate (0..1), p95_latency_ms, zero_result_rate (0..1) and avg_hits. A process-global
        aggregate with no per-collection scope.
        """
        return (await sdk.search.get_search_health()).model_dump(mode="json")
