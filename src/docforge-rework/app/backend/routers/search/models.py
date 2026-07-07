# ====== Code Summary ======
# Pydantic request/response models for the search router — the query in, and the ranked, hydrated
# chunk hits out. A hit is the flat, client-facing view of a SearchHit (the Postgres chunk row plus
# its fused Qdrant score); the rich chunk relations stay out of the vector path (lean-vector principle).

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    """
    A hybrid search over one collection.

    Attributes:
        query (str): The natural-language query, embedded with the collection's own embedder.
        limit (int): Number of fused results to return.
        filters (dict | None): Exact/any-of constraints on the collection's FILTERABLE fields —
            a scalar becomes an equality match, a list becomes a set-membership (any-of) match.
    """

    query: str = Field(min_length=1, description="The natural-language query to search for.")
    limit: int = Field(default=10, ge=1, le=100, description="Number of fused results.")
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Constraints on the FILTERABLE metadata fields (field → value or [values]).",
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
    """

    query: str = Field(description="The query that was searched.")
    hits: list[SearchHitModel] = Field(
        default_factory=list, description="Ranked hits, best first."
    )


__all__ = ["SearchRequest", "SearchHitModel", "SearchResponse"]
