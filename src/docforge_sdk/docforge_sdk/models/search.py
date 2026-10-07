# ====== Code Summary ======
# Request/response models for the search resource, mirrored field-for-field from the DocForge backend
# router models. ``filters`` and ``debug_info`` are opaque, server-shaped JSON and are typed as dicts.

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


class BlockLocation(BaseModel):
    """
    One source block's location on the page — enough for a UI to draw a box over the hit.

    Attributes:
        page (int | None): The page the block sits on. None for a page-less document (no page
            render) — distinct from a genuine 0-based page index 0.
        bbox (list[float]): The block's bounding box ``[x0, y0, x1, y1]``, NORMALISED to [0, 1] —
            multiply each component by the page image's width/height to draw it in pixels.
    """

    page: int | None = Field(
        description="The page the block sits on (0-based); None for a page-less document (no page "
        "render)."
    )
    page_number: int | None = Field(
        default=None,
        description="The same page, 1-based (as a reader counts it); None for a page-less document.",
    )
    bbox: list[float] = Field(
        description="Bounding box [x0, y0, x1, y1] NORMALISED to [0, 1] — multiply by the page "
        "image width/height to draw it in pixels.",
    )


class SearchHit(BaseModel):
    """
    One ranked search result — the flat view of a hydrated chunk hit.

    Attributes:
        chunk_id (str): The chunk's UUID (doubles as its Qdrant point id).
        document_id (str): The document the chunk belongs to.
        score (float): The fused RRF score (higher is better).
        text (str): The chunk's enriched text.
        chunk_index (int): The chunk's ordinal within its document.
        token_count (int): The chunk's token count.
        block_ids (list[str]): The IR block ids the chunk was assembled from (assembly order).
        page (int | None): The page of the chunk's primary (leading) block, 0-based.
        page_number (int | None): The same page, 1-based — the one to cite.
        bbox (list[float] | None): The primary block's NORMALISED [0, 1] bounding box.
        block_locations (list[BlockLocation]): Every source block's page + bbox (draw them all).

    Only ``chunk_id`` and ``document_id`` are always present: a request's ``return_fields`` omits the
    unrequested keys (absent, not null), so ``model_fields_set`` tells what the server really sent.
    """

    chunk_id: str = Field(description="The chunk's UUID.")
    document_id: str = Field(description="The owning document's UUID.")
    filename: str | None = Field(
        default=None, description="The source document's filename — the hit's human identity."
    )
    document_title: str | None = Field(
        default=None, description="The source document's title (empty parsed titles → null)."
    )
    heading_path: list[str] = Field(
        default_factory=list,
        description="The chunk's section ancestry, top-down (e.g. ['Article 7 — Audit rights']) — "
        "so a hit self-cites the section/clause it came from. Empty when the chunk sits under no "
        "section.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="The document's filterable metadata (field → value) — so a hit self-cites "
        "without a second GET /documents/{id}.",
    )
    score: float = Field(default=0.0, description="Fused RRF score (higher is better).")
    text: str = Field(default="", description="The chunk's enriched text.")
    chunk_index: int = Field(default=0, description="Ordinal within the document.")
    token_count: int = Field(default=0, description="Token count of the chunk.")
    block_ids: list[str] = Field(
        default_factory=list,
        description="The IR block ids the chunk was assembled from, in assembly order.",
    )
    page: int | None = Field(
        default=None,
        description="The page of the chunk's primary (leading) block, 0-based — where to draw the "
        "box. None when the chunk carries no block location.",
    )
    page_number: int | None = Field(
        default=None,
        description="The same page, 1-based (as a reader counts it) — cite this. None when unlocated.",
    )
    bbox: list[float] | None = Field(
        default=None,
        description="The primary block's bounding box [x0, y0, x1, y1], NORMALISED to [0, 1] — "
        "multiply by the page image width/height to draw it. None when unlocated.",
    )
    block_locations: list[BlockLocation] = Field(
        default_factory=list,
        description="Every source block's page + NORMALISED bbox — draw one box per block.",
    )
    fusion_score: float | None = Field(
        default=None,
        description="The retrieval fusion score before any rerank (only when the request set "
        "debug=true).",
    )
    rerank_score: float | None = Field(
        default=None,
        description="The cross-encoder rerank score (only when debug=true and a rerank stage "
        "re-scored the hit).",
    )


class SearchCost(BaseModel):
    """
    The priced cost of one search run's paid text-generation spend (query rewrite / HyDE).

    Attributes:
        prompt_tokens (int): Input tokens billed across the run's paid calls.
        completion_tokens (int): Output tokens billed across the run's paid calls.
        cost_usd (float | None): USD cost, or None when a paid call's model has no known rate.
        call_count (int): How many paid calls (usage-carrying leaves) the run made.
    """

    prompt_tokens: int = Field(description="Input tokens billed across the run's paid calls.")
    completion_tokens: int = Field(description="Output tokens billed across the run's paid calls.")
    cost_usd: float | None = Field(
        description="USD cost of the run's paid LLM spend, or None when a model that ran has no "
        "known rate."
    )
    call_count: int = Field(
        description="Number of paid calls (usage-carrying leaves) the run made."
    )


class SearchHint(BaseModel):
    """
    An actionable explanation about one filter, attached to a (200) search response.

    Attributes:
        field (str): The filtered metadata field the hint is about.
        value (Any): The filter value as sent.
        message (str): Human/agent-readable explanation.
        suggestions (list[str]): Closest stored values to retry with, best first (may be empty).
    """

    field: str = Field(description="The filtered metadata field the hint is about.")
    value: Any = Field(description="The filter value as sent (one list item, or the whole value).")
    message: str = Field(description="Human/agent-readable explanation of the problem.")
    suggestions: list[str] = Field(
        default_factory=list,
        description="Closest stored values of the field to retry with, best first (may be empty).",
    )


class SearchResponse(BaseModel):
    """
    The result of a hybrid search — the echoed query and its ranked hits.

    Attributes:
        query (str): The query that was searched (echoed for the client).
        hits (list[SearchHit]): The hydrated hits, best first.
        score_kind (str): What each hit's ``score`` represents — so the UI can label it correctly.
        cost (SearchCost | None): The run's priced paid-LLM spend, or None when no paid call was made.
        debug_info (dict[str, Any] | None): Non-fatal diagnostics; None when there is nothing to report.
        hints (list[SearchHint]): Actionable filter explanations (unknown value + closest stored values).
    """

    query: str = Field(description="The query that was searched.")
    hits: list[SearchHit] = Field(default_factory=list, description="Ranked hits, best first.")
    score_kind: str = Field(
        default="rrf_fusion",
        description="What every hit's ``score`` represents, so the UI labels it honestly: "
        "'rrf_fusion' (Reciprocal Rank Fusion of the dense+sparse branches — the default; "
        "rank-based, not a similarity), 'dbsf_fusion' (Distribution-Based Score Fusion), or "
        "'cross_encoder_rerank' (a cross-encoder relevance score, when reranking is enabled).",
    )
    cost: SearchCost | None = Field(
        default=None,
        description="The run's priced search-time LLM spend (query rewrite / HyDE), or None when no "
        "paid call was made.",
    )
    debug_info: dict[str, Any] | None = Field(
        default=None,
        description="Non-fatal diagnostics about how the search ran. None when empty.",
    )
    hints: list[SearchHint] = Field(
        default_factory=list,
        description="Actionable filter explanations: a filter value no document stores, with the "
        "closest stored values to retry with. Read these before concluding nothing exists.",
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


class ChunkBrowseResponse(BaseModel):
    """
    One page of browsed chunks.

    Attributes:
        chunks (list[SearchHit]): The page, ordered by document id then chunk_index (no score).
        next_cursor (str | None): Pass back as ``cursor`` for the next page; None on the last page.
        hints (list[SearchHint]): Filter hints (a value nothing stores; the culprit of an empty page).
    """

    chunks: list[SearchHit] = Field(
        default_factory=list, description="The page's chunks in browse order."
    )
    next_cursor: str | None = Field(
        default=None, description="Cursor of the next page; null on the last page."
    )
    hints: list[SearchHint] = Field(default_factory=list, description="Filter hints, as search.")


class SearchHealthSummary(BaseModel):
    """
    A compact, tile-friendly roll-up of search-runtime health for the deployment cockpit.

    Search runs INLINE in the request (no job/fleet surface), so this mirrors the operational tiles
    the jobs endpoints power. Every figure is CUMULATIVE since process start, read off the in-process
    ``docforge_search_*`` Prometheus series. Trends over time live in Grafana; this is the snapshot.

    Attributes:
        total_runs (int): Total search runs since process start (router 4xx rejections not counted).
        error_rate (float): Failed/timeout/unavailable runs over total, in [0, 1] (0.0 when none).
        p95_latency_ms (float | None): 95th-percentile whole-run latency in ms (bucket approximation);
            None when no run has been recorded yet.
        zero_result_rate (float): Zero-result runs over total, in [0, 1] (0.0 when none).
        avg_hits (float | None): Mean delivered hits per successful search; None when none observed.
    """

    total_runs: int = Field(
        description="Total search runs since process start (router 4xx rejections are not counted)."
    )
    error_rate: float = Field(
        description="Failed/timeout/unavailable runs over total, in [0, 1] (0.0 when total_runs==0).",
    )
    p95_latency_ms: float | None = Field(
        description="95th-percentile whole-run latency in ms (bucket-based approximation); None when "
        "no run has been recorded yet.",
    )
    zero_result_rate: float = Field(
        description="Zero-result runs over total, in [0, 1] (0.0 when total_runs==0).",
    )
    avg_hits: float | None = Field(
        description="Mean delivered hits per search over successful runs; None when none observed.",
    )


__all__ = [
    "SearchTarget",
    "SearchRequest",
    "BlockLocation",
    "SearchHit",
    "SearchCost",
    "SearchHint",
    "SearchResponse",
    "ChunkBrowseRequest",
    "ChunkBrowseResponse",
    "SearchHealthSummary",
]
