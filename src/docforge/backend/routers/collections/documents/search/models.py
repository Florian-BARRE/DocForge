# ====== Code Summary ======
# Request/response models for the Search section (collection + per-document hybrid retrieval).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """A hybrid search request."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, Any] | None = Field(default=None, description="Qdrant payload filter.")
    weights: dict[str, float] | None = Field(default=None, description="Per-vector fusion weight overrides.")


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


class SearchResponse(BaseModel):
    """Ranked results for a search query."""

    collection_id: uuid.UUID
    query: str
    total: int
    results: list[SearchResultItem]
    note: str | None = Field(default=None, description="Optional informational note (e.g. search not available).")
