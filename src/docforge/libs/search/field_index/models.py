# ====== Code Summary ======
# Data structures and constants for the multi-field hybrid index (spec §7.2, §9):
# canonical content vector names, the RRF rank constant, and the FieldVec / VectorPlan
# dataclasses describing which named vectors a collection's metadata schema requires.
# Small, tightly-coupled dataclasses + constants grouped intentionally.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical content vector names (always present), shared with the Qdrant client.
CONTENT_DENSE: str = "content_dense"
CONTENT_SPARSE: str = "content_bm25"

# RRF rank constant (standard k=60; larger → flatter rank influence).
RRF_K: int = 60


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
