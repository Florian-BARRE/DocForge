# ====== Code Summary ======
# Pydantic request/response models for the search router — the query in, and the ranked, hydrated
# chunk hits out. A hit is the flat, client-facing view of a hydrated chunk hit (the Postgres chunk
# row plus its fused Qdrant score); the rich chunk relations stay out of the vector path (lean-vector).

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchTargetModel(BaseModel):
    """
    One field to search and the modalities to search it on (the client-facing SearchTarget mirror).

    Attributes:
        field (str): The field to search — ``"content"`` (the chunk body) or a metadata field name.
        semantic (bool): Query the field's dense vector (semantic similarity).
        lexical (bool): Query the field's sparse BM25 vector (lexical match).
    """

    model_config = ConfigDict(extra="forbid")

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
        filters (dict | None): Constraints on the collection's FILTERABLE fields — a scalar becomes
            an equality match, a list becomes a set-membership (any-of) match, and a mapping of range
            bounds (``gte``/``gt``/``lte``/``lt``) becomes a numeric or datetime range (e.g.
            ``{"published": {"gte": "2024-01-01", "lte": "2024-12-31"}}`` or ``{"pages": {"gt": 10}}``).
            A range on a non-range-typed (keyword/bool) field, or a malformed range, is rejected 422.
        search_in (list[SearchTargetModel] | None): What to search — the fields (content and/or
            metadata) and modalities (semantic/lexical). None searches content on both axes
            (unchanged default). A target naming a vector the collection never indexed → 422.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="The natural-language query to search for.")
    limit: int = Field(default=10, ge=1, le=100, description="Number of fused results.")
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Constraints on the FILTERABLE metadata fields — field → a scalar (equality), "
        "a list (any-of), or a range mapping of gte/gt/lte/lt bounds (numeric or ISO-8601 datetime, "
        'e.g. {"published": {"gte": "2024-01-01", "lte": "2024-12-31"}}).',
    )
    search_in: list[SearchTargetModel] | None = Field(
        default=None,
        description="Fields × modalities to search (content and/or metadata). None → content on "
        "both semantic and lexical (the unchanged default).",
    )

    @field_validator("query")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Reject a whitespace-only query — embedding it would spend on nothing."""
        # min_length=1 lets " " through; strip and fail so a blank query never reaches the embedder.
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class BlockLocationModel(BaseModel):
    """
    One source block's location on the page — enough for a UI to draw a box over the hit.

    Attributes:
        page (int | None): The page the block sits on (as stored on the IR block). None for a
            page-less document (no page render) — distinct from a genuine 0-based page index 0.
        bbox (list[float]): The block's bounding box as ``[x0, y0, x1, y1]``, NORMALISED to [0, 1] —
            the frontend multiplies each component by the page image's width/height to get pixels.
    """

    page: int | None = Field(
        description="The page the block sits on; None for a page-less document (no page render).",
    )
    bbox: list[float] = Field(
        description="Bounding box [x0, y0, x1, y1] NORMALISED to [0, 1] — multiply by the page "
        "image width/height to draw it in pixels.",
    )


class SearchHitModel(BaseModel):
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
        block_locations (list[BlockLocationModel]): Every source block's page + bbox (draw them all).
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
    score: float = Field(
        description="The hit's ranking score, higher is better. Its meaning is given by the "
        "response-level ``score_kind``: for the default hybrid retrieval it is Qdrant's SERVER-SIDE "
        "FUSION score (Reciprocal Rank Fusion by default, or DBSF) — a RANK-based aggregate, NOT a "
        "cosine similarity or a 0-1 probability; when reranking is enabled it is the cross-encoder "
        "relevance score instead. The absolute magnitude is NOT comparable across queries or "
        "collections — only the relative ordering WITHIN one response is meaningful. On a tiny corpus "
        "(e.g. a single document) the top hit's score can legitimately pin to a round value like "
        "1.0000 — that is expected, not a bug.",
    )
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
    block_locations: list[BlockLocationModel] = Field(
        default_factory=list,
        description="Every source block's page + NORMALISED bbox — draw one box per block. Empty "
        "when the chunk carries no block location.",
    )


class SearchCostModel(BaseModel):
    """
    The priced cost of a single search run's paid text-generation spend.

    Search-time LLM calls (query rewrite / HyDE) are metered like ingestion: their token usage is
    summed over the run and priced against the collection's OWN effective rates (the same numbers the
    estimator and the ingest meter use). A stock search that runs no paid LLM reports zero tokens and
    a 0.0 cost; ``cost_usd`` is null (never a fabricated 0) when a model that DID run has no known rate.

    Attributes:
        prompt_tokens (int): Input tokens billed across the run's paid calls.
        completion_tokens (int): Output tokens billed across the run's paid calls.
        cost_usd (float | None): USD cost, or null when a paid call's model has no known rate.
        call_count (int): How many paid calls (leaves carrying usage) the run made.
    """

    prompt_tokens: int = Field(description="Input tokens billed across the run's paid calls.")
    completion_tokens: int = Field(description="Output tokens billed across the run's paid calls.")
    cost_usd: float | None = Field(
        description="USD cost of the run's paid LLM spend, or null when a model that ran has no "
        "known rate (tokens shown, cost '—')."
    )
    call_count: int = Field(
        description="Number of paid calls (usage-carrying leaves) the run made."
    )


class SearchResponse(BaseModel):
    """
    The result of a hybrid search — the echoed query and its ranked hits.

    Attributes:
        query (str): The query that was searched (echoed for the client).
        hits (list[SearchHitModel]): The hydrated hits, best first.
        score_kind (str): What each hit's ``score`` represents — so the UI can label it correctly.
        cost (SearchCostModel | None): The run's priced paid-LLM spend (rewrite/HyDE), or None when
            the run made no paid call (a stock lexical/dense search with no query-side LLM).
        debug_info (dict | None): Non-fatal diagnostics about how the search ran. None when there
            is nothing to report.
    """

    query: str = Field(description="The query that was searched.")
    hits: list[SearchHitModel] = Field(default_factory=list, description="Ranked hits, best first.")
    cost: SearchCostModel | None = Field(
        default=None,
        description="The run's priced search-time LLM spend (query rewrite / HyDE), or null when no "
        "paid call was made.",
    )
    score_kind: str = Field(
        default="rrf_fusion",
        description="What every hit's ``score`` represents, so the UI labels it honestly: "
        "'rrf_fusion' (Reciprocal Rank Fusion of the dense+sparse branches — the default; "
        "rank-based, not a similarity), 'dbsf_fusion' (Distribution-Based Score Fusion), or "
        "'cross_encoder_rerank' (a cross-encoder relevance score, when reranking is enabled). "
        "Fusion scores are only comparable within one response; a round 1.0000 on a tiny/single-doc "
        "corpus is normal.",
    )
    debug_info: dict[str, Any] | None = Field(
        default=None,
        description="Non-fatal diagnostics about how the search ran. None when empty.",
    )


__all__ = [
    "SearchTargetModel",
    "SearchRequest",
    "BlockLocationModel",
    "SearchHitModel",
    "SearchCostModel",
    "SearchResponse",
]
