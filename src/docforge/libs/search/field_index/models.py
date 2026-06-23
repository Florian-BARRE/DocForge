# ====== Code Summary ======
# Data structures and constants for the multi-field hybrid index (spec §7.2, §9):
# canonical content vector names, the RRF rank constant, and the FieldVec / VectorPlan
# dataclasses describing which named vectors a collection's metadata schema requires.
# Small, tightly-coupled dataclasses + constants grouped intentionally.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Canonical content vector names (always present), shared with the Qdrant client.
CONTENT_DENSE: str = "content_dense"
CONTENT_SPARSE: str = "content_bm25"

# RRF rank constant (standard k=60; larger → flatter rank influence).
RRF_K: int = 60


@dataclass(frozen=True, slots=True)
class RetrievalTuning:
    """
    Runtime retrieval tuning resolved from ``RetrieveConfig`` (collection contract).

    Built once per request by the search engine and threaded down through the
    retrieval stack (service → Qdrant client → search helpers).  Every default
    matches the historical hard-coded value, so ``RetrievalTuning()`` reproduces the
    pre-existing retrieval behavior exactly (weighted RRF, k=60, candidate_limit =
    max(top_k*3, 20), all vectors, no score threshold).

    Lives in field_index (not hybrid) because the Qdrant storage layer consumes it,
    and storage may only depend on this shared low-level module — never on hybrid.

    Attributes:
        vector_mode (str): "hybrid" (dense + sparse), "dense", or "sparse".
        fusion (str): "rrf" (reciprocal rank) or "dbsf" (distribution-based score).
        rrf_k (int): RRF rank constant.
        candidate_multiplier (int): candidate_limit = max(top_k * this, min_candidates).
        min_candidates (int): Floor for candidate_limit.
        score_threshold (float | None): Per-vector minimum similarity; None disables.
        field_weights (dict[str, float]): Per-field fusion weight (by field name).
        content_dense_weight (float): Fusion weight for the chunk-body dense vector.
        content_sparse_weight (float): Fusion weight for the chunk-body BM25 vector.
    """

    vector_mode: str = "hybrid"
    fusion: str = "rrf"
    rrf_k: int = 60
    candidate_multiplier: int = 3
    min_candidates: int = 20
    score_threshold: float | None = None
    field_weights: dict[str, float] = field(default_factory=dict)
    content_dense_weight: float = 1.0
    content_sparse_weight: float = 1.0

    @classmethod
    def from_config(cls, retrieve_cfg: Any) -> RetrievalTuning:
        """
        Build a RetrievalTuning from a ``RetrieveConfig`` (or any object exposing the
        same attributes).  ``None`` yields the all-defaults tuning.

        Args:
            retrieve_cfg (Any): A RetrieveConfig instance, or None.

        Returns:
            RetrievalTuning: Frozen runtime tuning.
        """
        if retrieve_cfg is None:
            return cls()
        return cls(
            vector_mode=getattr(retrieve_cfg, "vector_mode", "hybrid"),
            fusion=getattr(retrieve_cfg, "fusion", "rrf"),
            rrf_k=getattr(retrieve_cfg, "rrf_k", 60),
            candidate_multiplier=getattr(retrieve_cfg, "candidate_multiplier", 3),
            min_candidates=getattr(retrieve_cfg, "min_candidates", 20),
            score_threshold=getattr(retrieve_cfg, "score_threshold", None),
            field_weights=dict(getattr(retrieve_cfg, "field_weights", {}) or {}),
            content_dense_weight=getattr(retrieve_cfg, "content_dense_weight", 1.0),
            content_sparse_weight=getattr(retrieve_cfg, "content_sparse_weight", 1.0),
        )

    def candidate_limit(self, top_k: int) -> int:
        """
        Compute the per-vector candidate limit for a given top_k.

        Args:
            top_k (int): Number of final results requested.

        Returns:
            int: ``max(top_k * candidate_multiplier, min_candidates)``.
        """
        return max(top_k * self.candidate_multiplier, self.min_candidates)


@dataclass(slots=True)
class FieldVec:
    """A metadata field promoted to a vector, with its fusion weight."""

    name: str          # original field name (e.g. "title")
    vector: str        # Qdrant named-vector key (e.g. "meta_title_dense")
    weight: float      # RRF fusion weight from the schema


@dataclass(slots=True)
class VectorPlan:
    """
    The named vectors a collection's metadata schema requires (beyond content).

    Attributes:
        dense (list[FieldVec]): One per ``semantic`` field — a dedicated named dense vector.
        sparse (list[FieldVec]): One per ``lexical`` field — a dedicated named sparse (BM25) vector.
    """

    dense: list[FieldVec] = field(default_factory=list)
    sparse: list[FieldVec] = field(default_factory=list)

    @property
    def dense_vector_names(self) -> list[str]:
        """Return the Qdrant named-vector keys for all semantic fields."""
        return [f.vector for f in self.dense]

    @property
    def sparse_vector_names(self) -> list[str]:
        """Return the Qdrant named-vector keys for all lexical fields."""
        return [f.vector for f in self.sparse]
