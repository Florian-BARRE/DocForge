# ====== Code Summary ======
# MCP tools for the search domain — thin wrapper over sdk.search (a single collection-scoped
# retrieval route; there is no per-document search in the DocForge API).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Annotated, Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, SearchRequest, SearchTarget
from mcp.server.fastmcp import FastMCP
from pydantic import Field

_Scalar = str | int | float | bool

# The documented value forms of one `filters` entry; module-level so FastMCP can resolve it from
# the (lazy, `from __future__ import annotations`) signature and emit it in the tool's JSON schema.
FilterValue = _Scalar | list[_Scalar] | dict[Literal["gte", "gt", "lte", "lt"], int | float | str]

_FILTERS_DOC = (
    "Constraints on FILTERABLE metadata fields: {field_name: value}. Value forms: a scalar = "
    "equality (strings match case-insensitively); a list = any-of; "
    '{"gte"|"gt"|"lte"|"lt": number-or-ISO-datetime} = a range on number/datetime fields; text '
    'fields use full-text matching. Example: {"topic": "billing", "year": {"gte": 2023}}. '
    "Use describe_collection to see each field's real example values."
)


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register search tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def search_collection(
        collection_id: str,
        query: Annotated[str, Field(min_length=1, description="Natural-language query.")],
        limit: Annotated[int, Field(ge=1, le=100, description="Number of hits to return.")] = 10,
        filters: Annotated[dict[str, FilterValue] | None, Field(description=_FILTERS_DOC)] = None,
        search_in: Annotated[
            list[SearchTarget] | None,
            Field(
                description="Fields x modalities to search: [{field: 'content' or a metadata "
                "field name, semantic: bool, lexical: bool}]. Omit to search the chunk body "
                "('content') on both semantic and lexical axes. describe_collection lists the "
                "valid targets."
            ),
        ] = None,
    ) -> Any:
        """
        Hybrid semantic + keyword search over a collection (dense + sparse fusion).

        Call describe_collection(collection_id) FIRST: it lists the fields (meaning, type, real
        example values), the valid search_in targets, the filter grammar and ready-to-use example
        requests. Filters only work on FILTERABLE fields and unknown arguments are rejected.

        Returns {query, hits, score_kind, cost, debug_info, hints}. Each hit carries chunk_id,
        document_id, document_title, filename, heading_path, page_number (1-based - cite this, not
        the 0-based `page`), score, text, chunk_index, token_count, the document's filterable
        `metadata`, plus bbox/block_locations geometry. `hints`: when a filter value matches no
        stored value (e.g. a typo or the wrong spelling) the response carries hints naming the
        field with the closest stored values - read them before concluding nothing exists, and
        retry with a suggestion.
        """
        request = SearchRequest(query=query, limit=limit, filters=filters, search_in=search_in)
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
