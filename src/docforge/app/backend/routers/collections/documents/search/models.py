# ====== Code Summary ======
# Request/response models for the Search section (collection + per-document hybrid retrieval).
# When SearchRequest.debug is True, each SearchResultItem carries vector_ranks — a map of
# vector name → 1-indexed rank in that vector's candidate list — so callers can see WHY
# a chunk was surfaced (dense-only, sparse-only, or both).

# ====== Standard Library Imports ======
import uuid
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class SearchOverrides(BaseModel):
    """
    Per-REQUEST search overrides for the Search Lab.

    Every field is optional. When a field is present it SHADOWS the collection's stored
    ``pipeline.search`` config for THIS request only — nothing is ever persisted. Omitting the
    whole object (or leaving every field None) reproduces the collection's saved search behavior
    exactly. Enum values are validated by Pydantic (a bad value is a 422); unknown keys are
    rejected (``extra="forbid"``) so a typo'd override never silently no-ops.

    Attributes:
        vector_mode: Which named vectors to query — dense (semantic), sparse (keyword), or hybrid.
        fusion: Multi-vector fusion method — rrf (reciprocal rank) or dbsf (distribution-based).
        query_transform_strategy: Query expansion — none, rewrite, hyde, or multi_query.
        rerank_enabled: Toggle the cross-encoder rerank stage for this query.
    """

    model_config = ConfigDict(extra="forbid")

    vector_mode: Literal["dense", "sparse", "hybrid"] | None = Field(
        default=None, description="Override pipeline.search.retrieve.vector_mode for this query."
    )
    fusion: Literal["rrf", "dbsf"] | None = Field(
        default=None, description="Override pipeline.search.retrieve.fusion for this query."
    )
    query_transform_strategy: Literal["none", "rewrite", "hyde", "multi_query"] | None = Field(
        default=None,
        description="Override pipeline.search.query_transform.strategy for this query.",
    )
    rerank_enabled: bool | None = Field(
        default=None, description="Override pipeline.search.rerank.enabled for this query."
    )


class SearchRequest(BaseModel):
    """A hybrid search request."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, Any] | None = Field(default=None, description="Qdrant payload filter.")
    weights: dict[str, float] | None = Field(
        default=None, description="Per-vector fusion weight overrides."
    )
    overrides: SearchOverrides | None = Field(
        default=None,
        description=(
            "Optional per-request search overrides (Search Lab). When present, the listed fields "
            "shadow the collection's saved pipeline.search for THIS query only — never persisted. "
            "Omit for the collection's saved search behavior."
        ),
    )
    debug: bool = Field(
        default=False,
        description=(
            "When true, include per-vector rank breakdown in each result "
            "(vector_ranks field). Slightly slower — uses the debug search path."
        ),
    )


class SearchResultItem(BaseModel):
    """One ranked chunk in a search response."""

    chunk_id: str
    document_id: str
    score: float
    raw_text: str
    strategy: str
    token_count: int
    pages: list[int] = []
    block_ids: list[str] = []
    vector_ranks: dict[str, int] | None = Field(
        default=None,
        description=(
            "Per-vector name → 1-indexed rank in that vector's candidate list. "
            "Present only when SearchRequest.debug is True. "
            "A chunk absent from a vector's list has no entry for that key. "
            "Example: {\"dense-text\": 1, \"sparse-text\": 4} means the chunk was "
            "#1 by semantic similarity and #4 by keyword matching."
        ),
    )


class SearchGroupItem(BaseModel):
    """One document group when grouping is enabled (document-level results)."""

    document_id: str
    score: float = Field(..., description="Best chunk score in the group (group ordering key).")
    chunks: list[SearchResultItem] = Field(
        default_factory=list, description="The group's chunks, best-first, capped at group_size."
    )


class SearchResponse(BaseModel):
    """Ranked results for a search query."""

    collection_id: uuid.UUID
    query: str
    total: int
    results: list[SearchResultItem]
    groups: list[SearchGroupItem] | None = Field(
        default=None,
        description=(
            "Document-level groups, present only when pipeline.search.retrieve.grouping "
            "is enabled. When set, `results` is the groups flattened in group order."
        ),
    )
    note: str | None = Field(
        default=None,
        description="Optional informational note (e.g. search not available, sparse unavailable).",
    )
    debug_info: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Vector plan used for this query (present when debug=True): "
            "dense_vectors, sparse_vectors, fusion weights, candidate_limit."
        ),
    )
