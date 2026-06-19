# ====== Code Summary ======
# Pydantic-free data models for hybrid search results.
# SearchResult is a plain dataclass consumed by the service layer and
# mapped to API response models in the search router.

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
