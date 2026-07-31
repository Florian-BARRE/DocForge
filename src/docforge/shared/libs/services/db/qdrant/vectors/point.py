# ====== Code Summary ======
# The clean, qdrant-free input types for the store: a `SparseVec` (BM25 indices+values) and a
# `QdrantPoint` (its id = the chunk id, its named dense/sparse vectors, and its LEAN payload). The
# Database façade builds these; QdrantStore converts them to qdrant-client structs internally, so
# qdrant types never leak upward.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SparseVec:
    """A sparse (BM25) vector — parallel index/value lists."""

    indices: list[int]
    values: list[float]


@dataclass(slots=True)
class QdrantPoint:
    """One point to upsert: the chunk id, its named vectors, and its lean payload."""

    point_id: str
    payload: dict[str, Any]
    dense: dict[str, list[float]] = field(default_factory=dict)  # vector name → dense vector
    sparse: dict[str, SparseVec] = field(default_factory=dict)  # vector name → sparse vector


__all__ = ["SparseVec", "QdrantPoint"]
