# ====== Code Summary ======
# DeclaredVectors — what a live Qdrant store ACTUALLY declares: its dense and sparse named vectors
# plus which sparse vectors carry the IDF modifier. Compared against the config-derived VectorLayout,
# it yields the sparse vectors whose modifier disagrees with the configured sparse provider (another
# encoder's vectors — e.g. local-BM25 meta vectors under a bge_server sparse config): those are
# treated as missing (rebuild required), never queried nor written as is.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout

# ====== Local Project Imports ======
from .vector_schema import QdrantVectorSchema


@dataclass(frozen=True, slots=True)
class DeclaredVectors:
    """The named vectors a store declares (dense, sparse) and its IDF-declared sparse subset."""

    dense: frozenset[str] = field(default_factory=frozenset)
    sparse: frozenset[str] = field(default_factory=frozenset)
    idf_sparse: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_params(cls, params: Any) -> "DeclaredVectors":
        """
        Read the declared vectors off a collection's ``config.params``.

        Args:
            params (Any): ``(await client.get_collection(name)).config.params``.

        Returns:
            DeclaredVectors: The declared names (DocForge always uses NAMED vectors).
        """
        dense = params.vectors if isinstance(params.vectors, dict) else {}
        sparse = params.sparse_vectors or {}
        return cls(
            dense=frozenset(dense),
            sparse=frozenset(sparse),
            idf_sparse=frozenset(n for n, p in sparse.items() if QdrantVectorSchema.is_idf(p)),
        )

    def mismatched(self, layout: VectorLayout) -> frozenset[str]:
        """The declared sparse vectors whose IDF modifier differs from what the layout requires."""
        return frozenset(n for n in self.sparse if (n in self.idf_sparse) != layout.sparse_idf)

    def pair(self) -> tuple[set[str], set[str]]:
        """The legacy ``(dense, sparse)`` name sets."""
        return set(self.dense), set(self.sparse)


__all__ = ["DeclaredVectors"]
