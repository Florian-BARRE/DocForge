# ====== Code Summary ======
# Pydantic request/response models for the search router — the query in, and the ranked, hydrated
# chunk hits out. A hit is the flat, client-facing view of a hydrated chunk hit (the Postgres chunk
# row plus its fused Qdrant score); the rich chunk relations stay out of the vector path (lean-vector).

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, field_validator


class SearchTargetModel(BaseModel):
    """
    One field to search and the modalities to search it on (the client-facing SearchTarget mirror).

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
        filters (dict | None): Exact/any-of constraints on the collection's FILTERABLE fields —
            a scalar becomes an equality match, a list becomes a set-membership (any-of) match.
        search_in (list[SearchTargetModel] | None): What to search — the fields (content and/or
            metadata) and modalities (semantic/lexical). None searches content on both axes
            (unchanged default). A target naming a vector the collection never indexed → 422.
        use_late_interaction (bool | None): Opt into the ColBERT re-score. None → off for this
            query; True/False sets it for this query.
        rescore_pool_size (int | None): Size of the fused candidate pool the ColBERT stage
            re-scores. None → the retrieve node's own config / the store default governs.
    """

    query: str = Field(min_length=1, description="The natural-language query to search for.")
    limit: int = Field(default=10, ge=1, le=100, description="Number of fused results.")
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Constraints on the FILTERABLE metadata fields (field → value or [values]).",
    )
    search_in: list[SearchTargetModel] | None = Field(
        default=None,
        description="Fields × modalities to search (content and/or metadata). None → content on "
        "both semantic and lexical (the unchanged default).",
    )
    use_late_interaction: bool | None = Field(
        default=None,
        description="Opt into the ColBERT late-interaction re-score for this query. None → off.",
    )
    rescore_pool_size: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Fused candidate pool size the ColBERT stage re-scores. None → the retrieve "
        "node's own config / the store default governs.",
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
    """

    chunk_id: str = Field(description="The chunk's UUID.")
    document_id: str = Field(description="The owning document's UUID.")
    score: float = Field(description="Fused RRF score (higher is better).")
    text: str = Field(description="The chunk's enriched text.")
    chunk_index: int = Field(description="Ordinal within the document.")
    token_count: int = Field(description="Token count of the chunk.")


class SearchResponse(BaseModel):
    """
    The result of a hybrid search — the echoed query and its ranked hits.

    Attributes:
        query (str): The query that was searched (echoed for the client).
        hits (list[SearchHitModel]): The hydrated hits, best first.
        debug_info (dict | None): Non-fatal diagnostics about how the search ran — e.g. a note
            that late interaction was requested but skipped because the collection carries no
            ColBERT vectors. None when there is nothing to report.
    """

    query: str = Field(description="The query that was searched.")
    hits: list[SearchHitModel] = Field(default_factory=list, description="Ranked hits, best first.")
    debug_info: dict[str, Any] | None = Field(
        default=None,
        description="Non-fatal diagnostics (e.g. late_interaction_skipped). None when empty.",
    )


__all__ = ["SearchTargetModel", "SearchRequest", "SearchHitModel", "SearchResponse"]
