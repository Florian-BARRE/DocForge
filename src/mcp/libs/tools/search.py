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

# ====== Local Project Imports ======
from ..compact_json import compact_json
from .search_rendering import AGENT_RETURN_FIELDS, SearchTextRenderer

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
        return_fields: Annotated[
            list[str] | None,
            Field(
                description="Hit fields to return. Omit for the agent default (text, "
                "document_title, page_number, heading_path, score, metadata - plus chunk_id and "
                "document_id, always returned). Allowed: any hit field (filename, "
                "document_title, heading_path, metadata, score, text, chunk_index, token_count, "
                "block_ids, page, page_number, bbox, block_locations) or 'metadata.<field>' for one "
                "metadata entry. Unknown names are rejected."
            ),
        ] = None,
        group_by: Annotated[
            Literal["document"] | None,
            Field(
                description="'document' = at most max_per_document hits per document (diverse "
                "sources instead of one document repeated). Omit for plain ranking."
            ),
        ] = None,
        max_per_document: Annotated[
            int | None,
            Field(ge=1, le=10, description="Per-document hit cap (default 1); needs group_by."),
        ] = None,
        format: Annotated[
            Literal["text", "json"],
            Field(
                description="'text' (default) = one readable block per hit with a citation line; "
                "'json' = the compact structured response."
            ),
        ] = "text",
    ) -> Any:
        """
        Hybrid semantic + keyword search over a collection (dense + sparse fusion).

        Call describe_collection(collection_id) FIRST: it lists the fields (meaning, type, real
        example values), the valid search_in targets, the filter grammar and ready-to-use example
        requests. Filters only work on FILTERABLE fields and unknown arguments are rejected.

        OUTPUT (format="text", the default): a header `N hits for "<query>"`, then per hit
        `[rank] <title> | p.<page_number> | <heading > path> | score <s> | doc <id> |
        chunk <id>`, an optional `meta: k=v; ...` line (the document's filterable metadata) and the
        chunk text, then `Hint: ...` lines. page_number is 1-based - cite it. Cite title + page;
        doc/chunk ids feed the explorer/document tools. Hints: when a filter value matches no
        stored value (typo, wrong spelling) a hint names the field and the closest stored values -
        read them before concluding nothing exists, and retry with a suggestion.

        format="json": the compact (non-indented) response {query, hits, score_kind, cost,
        debug_info, hints}; each hit holds ONLY the requested return_fields (+ chunk_id,
        document_id); a key you did not request is absent, a requested key the server sent as
        null stays null. Geometry (bbox, block_locations - normalised page coordinates, ~70% of a
        full hit's size) is NOT in the default fields: ask for it with
        format="json" and return_fields including "block_locations" / "bbox" / "page".

        group_by="document": use it for broad questions or when the top hits are one document
        repeated - each document contributes at most max_per_document hits (default 1), the next
        best documents fill the page, so fewer than `limit` hits can come back on a small
        collection. Leave it off to read several passages of the same document.
        """
        # 1. Build the request; the agent default projection applies unless the caller chose one
        request = SearchRequest(
            query=query,
            limit=limit,
            filters=filters,
            search_in=search_in,
            return_fields=return_fields if return_fields is not None else AGENT_RETURN_FIELDS,
            group_by=group_by,
            **({"max_per_document": max_per_document} if max_per_document is not None else {}),
        )
        result = await sdk.search.search(collection_id, request)

        # 2. Text for reading, compact JSON (only what the server sent) for programmatic use
        if format == "json":
            return compact_json(result.model_dump(mode="json", exclude_unset=True))
        return SearchTextRenderer().render(result)

    @mcp.tool()
    async def get_search_health() -> Any:
        """
        Deployment-wide search-runtime health summary (cumulative since process start).

        Search runs inline (no job/fleet surface), so this is the operational snapshot: total_runs,
        error_rate (0..1), p95_latency_ms, zero_result_rate (0..1) and avg_hits. A process-global
        aggregate with no per-collection scope.
        """
        return (await sdk.search.get_search_health()).model_dump(mode="json")
