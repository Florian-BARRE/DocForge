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
        hits (list[SearchHit]): The hydrated hits, best first.
        debug_info (dict[str, Any] | None): Non-fatal diagnostics; None when there is nothing to report.
    """

    query: str = Field(description="The query that was searched.")
    hits: list[SearchHit] = Field(default_factory=list, description="Ranked hits, best first.")
    debug_info: dict[str, Any] | None = Field(
        default=None,
        description="Non-fatal diagnostics about how the search ran. None when empty.",
    )


__all__ = ["SearchTarget", "SearchRequest", "SearchHit", "SearchResponse"]
