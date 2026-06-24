# ====== Code Summary ======
# Pydantic-free data models for hybrid search results.
# SearchResult is a plain dataclass consumed by the service layer and
# mapped to API response models in the search router.
# RetrievalTuning lives in libs.search.field_index (shared low-level module also
# used by the Qdrant storage layer) and is re-exported here for convenience.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchResult:
    """
    A single retrieval result returned by the hybrid search service.

    Attributes:
        chunk_id (str): UUID string — primary key in ``chunk`` table and Qdrant point.
        document_id (str): UUID string of the owning document.
        score (float): RRF fusion score from Qdrant (higher = more relevant).
        raw_text (str): Faithful chunk text for display / citation.
        strategy (str): Chunking strategy used to produce this chunk.
        token_count (int): Estimated token count of ``raw_text``.
        pages (list[int]): Source page numbers (0-indexed).
        config_hash (str): Hash of the S4 config that produced this chunk.
        block_ids (list[str]): IR block IDs contributing to this chunk.
    """

    chunk_id: str
    document_id: str
    score: float
    raw_text: str
    strategy: str
    token_count: int
    pages: list[int] = field(default_factory=list)
    config_hash: str = ""
    block_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DocumentGroup:
    """
    A group of chunks belonging to one document (document-level search result).

    Produced when ``RetrieveConfig.grouping`` is enabled: the flat fused chunk list is
    collapsed by ``document_id`` so the response carries the top documents, each with its
    best chunks, rather than a flat chunk list.

    Attributes:
        document_id (str): The grouping key (owning document).
        score (float): The best (highest) chunk score in the group — used to order groups.
        chunks (list[SearchResult]): The group's chunks, best-first, capped at group_size.
    """

    document_id: str
    score: float
    chunks: list[SearchResult] = field(default_factory=list)


@dataclass(slots=True)
class SearchOutcome:
    """
    The engine's search result: a flat ranked chunk list plus optional document groups.

    ``groups`` is populated only when ``RetrieveConfig.grouping`` is enabled; ``results``
    is always present (when grouped, it is the groups flattened in group order) so existing
    flat-list consumers keep working unchanged.

    Attributes:
        results (list[SearchResult]): Flat ranked chunks (group-flattened when grouping is on).
        groups (list[DocumentGroup] | None): Document-level groups, or None when disabled.
    """

    results: list[SearchResult] = field(default_factory=list)
    groups: list[DocumentGroup] | None = None
