# ====== Code Summary ======
# MCP tools for the search domain — thin wrapper over sdk.search (a single collection-scoped
# retrieval route; there is no per-document search in the DocForge API).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Annotated, Any, Literal

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, ChunkBrowseRequest, SearchRequest, SearchTarget
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ====== Local Project Imports ======
from ..compact_json import compact_json
from .search_rendering import AGENT_RETURN_FIELDS, BROWSE_RETURN_FIELDS, SearchTextRenderer

_Scalar = str | int | float | bool
_Bound = int | float | str


class FilterOperator(BaseModel):
    """One filter operator object: any subset of the backend's operator keys, nothing else.

    Per-type validity (e.g. no prefix on a number field) stays the server's call - it answers 422
    with the valid operators for the field.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    eq: _Scalar | None = Field(default=None, description="Equals this value.")
    in_: list[_Scalar] | None = Field(default=None, alias="in", description="Any of these values.")
    not_: _Scalar | list[_Scalar] | None = Field(
        default=None, alias="not", description="Exclude this value (or any of a list)."
    )
    not_in: list[_Scalar] | None = Field(default=None, description="Exclude all of these values.")
    contains: str | None = Field(default=None, description="Substring (case-insensitive).")
    prefix: str | None = Field(default=None, description="Prefix (case-insensitive).")
    exists: bool | None = Field(default=None, description="true = value present; false = absent.")
    gte: _Bound | None = Field(default=None, description="Range: >= (number or ISO datetime).")
    gt: _Bound | None = Field(default=None, description="Range: > (number or ISO datetime).")
    lte: _Bound | None = Field(default=None, description="Range: <= (number or ISO datetime).")
    lt: _Bound | None = Field(default=None, description="Range: < (number or ISO datetime).")

    @model_validator(mode="after")
    def _require_one_operator(self) -> FilterOperator:
        """Reject an empty operator object (it would constrain nothing)."""
        if not self.model_fields_set:
            raise ValueError("an operator object needs at least one operator key")
        return self


# The documented value forms of one `filters` entry; module-level so FastMCP can resolve it from
# the (lazy, `from __future__ import annotations`) signature and emit it in the tool's JSON schema.
FilterValue = _Scalar | list[_Scalar] | FilterOperator

_FILTERS_DOC = (
    "Constraints on FILTERABLE metadata fields, ANDed: {field_name: value}. Value forms: a scalar "
    "= equality (strings case-insensitive); a list = any-of; an operator object: "
    '{"eq"|"not": v}, {"in"|"not_in": [..]}, {"contains"|"prefix": "text"}, {"exists": bool}, '
    '{"gte"|"gt"|"lte"|"lt": number-or-ISO-datetime}. Example: {"topic": {"not": "legal"}, '
    '"title": {"contains": "audit"}, "year": {"gte": 2023}}. Call describe_collection for each '
    "field's type and allowed operators (a wrong operator for a type is refused with the valid ones)."
)


def _plain_filters(filters: dict[str, FilterValue] | None) -> dict[str, Any] | None:
    """Turn operator models back into the plain JSON the API expects (aliases, set keys only)."""
    if filters is None:
        return None
    return {
        k: v.model_dump(by_alias=True, exclude_unset=True) if isinstance(v, FilterOperator) else v
        for k, v in filters.items()
    }


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
        min_score: Annotated[
            float | None,
            Field(
                ge=0,
                description="Drop hits scoring below this (scale = score_kind; a "
                "cross-encoder rerank score is 0..1, fusion scores are only a coarse cut).",
            ),
        ] = None,
        rerank: Annotated[
            bool | None,
            Field(
                description="false = skip the reranker for this call (faster); true = require "
                "it. Omit = the collection's pipeline decides."
            ),
        ] = None,
        fusion: Annotated[
            Literal["rrf", "dbsf"] | None,
            Field(
                description="Override dense/sparse fusion: 'rrf' (rank-based) or 'dbsf' (a "
                "confident axis can dominate). Omit = the collection's setting."
            ),
        ] = None,
        debug: Annotated[
            bool,
            Field(description="true = also show each hit's fusion_score and rerank_score."),
        ] = False,
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
        requests. Filters only work on FILTERABLE fields and unknown arguments are rejected. The query
        must not be blank: to list passages by filter without a query, use browse_chunks.

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
            filters=_plain_filters(filters),
            search_in=search_in,
            return_fields=return_fields if return_fields is not None else AGENT_RETURN_FIELDS,
            group_by=group_by,
            min_score=min_score,
            rerank=rerank,
            fusion=fusion,
            debug=debug,
            **({"max_per_document": max_per_document} if max_per_document is not None else {}),
        )
        result = await sdk.search.search(collection_id, request)

        # 2. Text for reading, compact JSON (only what the server sent) for programmatic use
        if format == "json":
            return compact_json(result.model_dump(mode="json", exclude_unset=True))
        return SearchTextRenderer().render(result)

    @mcp.tool()
    async def browse_chunks(
        collection_id: str,
        filters: Annotated[dict[str, FilterValue] | None, Field(description=_FILTERS_DOC)] = None,
        limit: Annotated[int, Field(ge=1, le=200, description="Chunks per page.")] = 20,
        cursor: Annotated[
            str | None,
            Field(
                description="The previous page's next_cursor, with the SAME filters. Omit for "
                "the first page."
            ),
        ] = None,
        return_fields: Annotated[
            list[str] | None,
            Field(
                description="Chunk fields to return (as search_collection, minus score). Omit "
                "for the agent default: text, document_title, page_number, heading_path, "
                "metadata (+ chunk_id, document_id)."
            ),
        ] = None,
        format: Annotated[
            Literal["text", "json"],
            Field(description="'text' (default) = one block per chunk; 'json' = compact response."),
        ] = "text",
    ) -> Any:
        """
        List a document's / a filter's passages in reading order, without a query.

        Use it to read "all passages of document X" (filter on its identifier field) or to walk a
        process page by page; pass next_cursor back (with the same filters) to continue. Order is
        document then chunk position. For relevance-ranked retrieval use search_collection.
        Call describe_collection first for the filterable fields.

        OUTPUT (format="text"): per chunk `[n] <title> | p.<page_number> | <heading > path> | doc
        <id> | chunk <id>` then the text; then `next_cursor: <token>` (or `end of results`) and
        `Hint: ...` lines. format="json": the compact {chunks, next_cursor, hints}.
        """
        # 1. Build the request with the lean default projection
        request = ChunkBrowseRequest(
            filters=_plain_filters(filters),
            limit=limit,
            cursor=cursor,
            return_fields=return_fields if return_fields is not None else BROWSE_RETURN_FIELDS,
        )
        page = await sdk.search.browse(collection_id, request)

        # 2. Text for reading, compact JSON for programmatic use
        if format == "json":
            return compact_json(page.model_dump(mode="json", exclude_unset=True))
        return SearchTextRenderer().render_browse(page)

    @mcp.tool()
    async def get_search_health() -> Any:
        """
        Deployment-wide search-runtime health summary (cumulative since process start).

        Search runs inline (no job/fleet surface), so this is the operational snapshot: total_runs,
        error_rate (0..1), p95_latency_ms, zero_result_rate (0..1) and avg_hits. A process-global
        aggregate with no per-collection scope.
        """
        return (await sdk.search.get_search_health()).model_dump(mode="json")
