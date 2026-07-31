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
        filters (dict | None): Exact/any-of constraints on the collection's FILTERABLE fields —
            a scalar becomes an equality match, a list becomes a set-membership (any-of) match.
        search_in (list[SearchTargetModel] | None): What to search — the fields (content and/or
            metadata) and modalities (semantic/lexical). None searches content on both axes
            (unchanged default). A target naming a vector the collection never indexed → 422.
    """

    model_config = ConfigDict(extra="forbid")

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


class SearchResponse(BaseModel):
    """
    The result of a hybrid search — the echoed query and its ranked hits.

    Attributes:
        query (str): The query that was searched (echoed for the client).
        hits (list[SearchHitModel]): The hydrated hits, best first.
        debug_info (dict | None): Non-fatal diagnostics about how the search ran. None when there
            is nothing to report.
    """

    query: str = Field(description="The query that was searched.")
    hits: list[SearchHitModel] = Field(default_factory=list, description="Ranked hits, best first.")
    debug_info: dict[str, Any] | None = Field(
        default=None,
        description="Non-fatal diagnostics about how the search ran. None when empty.",
    )


__all__ = ["SearchTargetModel", "SearchRequest", "SearchHitModel", "SearchResponse"]
