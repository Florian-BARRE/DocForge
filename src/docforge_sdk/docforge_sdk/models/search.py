# ====== Code Summary ======
# Request/response models for the search resource, mirrored field-for-field from the DocForge backend
# router models. ``filters`` and ``debug_info`` are opaque, server-shaped JSON and are typed as dicts.

# ====== Standard Library Imports ======
from typing import Any

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
    """

    query: str = Field(min_length=1, description="The natural-language query to search for.")
    limit: int = Field(default=10, ge=1, le=100, description="Number of fused results.")
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Constraints on the FILTERABLE metadata fields (field → value or [values]).",
    )
    search_in: list[SearchTarget] | None = Field(
        default=None,
        description="Fields × modalities to search (content and/or metadata). None → content on "
        "both semantic and lexical (the unchanged default).",
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
        description="The page the block sits on; None for a page-less document (no page render)."
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
        page (int | None): The page of the chunk's primary (leading) block — draw the box here.
        bbox (list[float] | None): The primary block's NORMALISED [0, 1] bounding box.
        block_locations (list[BlockLocation]): Every source block's page + bbox (draw them all).
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
    score: float = Field(description="Fused RRF score (higher is better).")
    text: str = Field(description="The chunk's enriched text.")
    chunk_index: int = Field(description="Ordinal within the document.")
    token_count: int = Field(description="Token count of the chunk.")
    block_ids: list[str] = Field(
        default_factory=list,
        description="The IR block ids the chunk was assembled from, in assembly order.",
    )
    page: int | None = Field(
        default=None,
        description="The page of the chunk's primary (leading) block — where to draw the box. "
        "None when the chunk carries no block location.",
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


class SearchResponse(BaseModel):
    """
    The result of a hybrid search — the echoed query and its ranked hits.

    Attributes:
        query (str): The query that was searched (echoed for the client).
        hits (list[SearchHit]): The hydrated hits, best first.
        score_kind (str): What each hit's ``score`` represents — so the UI can label it correctly.
        cost (SearchCost | None): The run's priced paid-LLM spend, or None when no paid call was made.
        debug_info (dict[str, Any] | None): Non-fatal diagnostics; None when there is nothing to report.
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


__all__ = [
    "SearchTarget",
    "SearchRequest",
    "BlockLocation",
    "SearchHit",
    "SearchCost",
    "SearchResponse",
]
