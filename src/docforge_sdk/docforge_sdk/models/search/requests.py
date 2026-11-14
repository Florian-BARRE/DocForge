# ====== Code Summary ======
# Search request models: the search targets, the search request and the chunk-browse request.
# ``filters`` is opaque, server-shaped JSON and is typed as a dict.

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class SearchTarget(BaseModel):
    """
    One field to search and the modalities to search it on.

    Attributes:
        field (str): The field to search — ``"content"`` (the chunk body) or a metadata field name.
        semantic (bool): Query the field's dense vector (semantic similarity).
        lexical (bool): Query the field's sparse BM25 vector (lexical match).
    """

    field: str = Field(
        default="content",
        min_length=1,
        description="Field to search — 'content' (chunk body) or a metadata field name.",
    )
    semantic: bool = Field(
        default=False, description="Query the field's dense vector (semantic similarity)."
    )
    lexical: bool = Field(
        default=False, description="Query the field's sparse BM25 vector (lexical match)."
    )


class SearchRequest(BaseModel):
    """
    A hybrid search over one collection.

    Attributes:
        query (str): The natural-language query, embedded with the collection's own embedder.
        limit (int): Number of fused results to return.
        filters (dict[str, Any] | None): Exact/any-of constraints on the FILTERABLE fields.
        search_in (list[SearchTarget] | None): Fields × modalities to search. None → content on both.
        return_fields (list[str] | None): Hit fields to return (lean response). None → the full hit.
        group_by (Literal["document"] | None): ``"document"`` caps hits per document.
        max_per_document (int): The per-document cap under ``group_by`` (1-10).
        min_score (float | None): Drop hits scoring below this (scale = the response's score_kind).
        rerank (bool | None): Per-request override of the rerank stage (None = the pipeline decides).
        fusion (Literal["rrf", "dbsf"] | None): Per-request override of the dense/sparse fusion.
        debug (bool): Add each hit's ``fusion_score`` / ``rerank_score``.
    """

    query: str = Field(min_length=1, description="The natural-language query to search for.")
    limit: int = Field(default=10, ge=1, le=100, description="Number of fused results.")
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Metadata filters, ANDed across fields: {field: value}. A scalar = equality "
        "(string/enum/keyword_list match case-insensitively); a list = any-of (max 100); an object "
        '= ONE operator: {"eq": v}, {"in": [..]}, {"not": v}, {"not_in": [..]}, '
        '{"contains": "sub"} / {"prefix": "pre"} (string-ish fields: case-insensitive '
        'match against stored values; text fields: contains = full-text), {"exists": true|false}, '
        'or range bounds {"gte","gt","lte","lt"} on integer/float/datetime fields '
        "(datetime bounds = ISO-8601 strings). Only filterable fields; an operator not valid for the "
        "field type -> 422 listing the valid ones. A value no document stores yields a response hint "
        "with the closest stored values.",
    )
    search_in: list[SearchTarget] | None = Field(
        default=None,
        description="Fields × modalities to search (content and/or metadata). None → content on "
        "both semantic and lexical (the unchanged default).",
    )
    return_fields: list[str] | None = Field(
        default=None,
        max_length=64,
        description="The hit fields to return (a lean response): any hit field name (chunk_id, "
        "document_id, filename, document_title, heading_path, metadata, score, text, chunk_index, "
        "token_count, block_ids, page, page_number, bbox, block_locations) or 'metadata.<field>' to "
        "keep one metadata entry. chunk_id and document_id are ALWAYS returned. Omitted fields are "
        "ABSENT from each hit (not null). None → the full hit. An unknown name → 422.",
    )
    group_by: Literal["document"] | None = Field(
        default=None,
        description="'document' → no document contributes more than max_per_document hits; the "
        "ranking keeps its order and is filled with the next best hits of other documents. "
        "None → no grouping.",
    )
    max_per_document: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Per-document hit cap when group_by='document' (default 1). Only valid "
        "together with group_by.",
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        description="Drop hits whose final score is below this threshold (on the scale named by "
        "the response's score_kind). None -> no threshold.",
    )
    rerank: bool | None = Field(
        default=None,
        description="Override the collection's rerank stage for this request: false skips it, "
        "true requires it (422 when the search pipeline has none). None -> the pipeline decides.",
    )
    fusion: Literal["rrf", "dbsf"] | None = Field(
        default=None,
        description="Override how the dense and sparse branches are fused for this request: 'rrf' "
        "(rank-based) or 'dbsf' (distribution-based). None -> the collection's configured fusion.",
    )
    debug: bool = Field(
        default=False,
        description="True -> each hit also carries fusion_score and, when reranked, rerank_score.",
    )


class ChunkBrowseRequest(BaseModel):
    """
    List a collection's chunks by filter, without a query.

    Attributes:
        filters (dict[str, Any] | None): The same filter map as search; None -> every chunk.
        limit (int): Page size (1-200).
        cursor (str | None): The previous page's ``next_cursor``; None -> the first page.
        return_fields (list[str] | None): Chunk fields to return (as search; ``score`` is not one).
    """

    filters: dict[str, Any] | None = Field(
        default=None,
        description="Constraints on the FILTERABLE metadata fields - exactly the grammar of search "
        "`filters`. None -> every searchable chunk of the collection.",
    )
    limit: int = Field(default=20, ge=1, le=200, description="Chunks per page (1-200).")
    cursor: str | None = Field(
        default=None,
        description="Opaque cursor: the previous page's `next_cursor`, sent back unchanged with the "
        "SAME filters. None -> the first page.",
    )
    return_fields: list[str] | None = Field(
        default=None,
        max_length=64,
        description="The chunk fields to return - any search hit field except score, or "
        "'metadata.<field>'. chunk_id and document_id are ALWAYS returned. None -> every field "
        "except geometry (page_number is kept). Omitted fields are absent (not null).",
    )
