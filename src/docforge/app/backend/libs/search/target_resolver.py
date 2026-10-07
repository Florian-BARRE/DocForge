# ====== Code Summary ======
# TargetVectorResolver — the ONE place that knows how a SearchTarget maps to a Qdrant named vector.
# It fans the query's single dense/sparse vectors out over the requested targets: a semantic target
# names the query's dense vector under the field's dense name, a lexical target names its sparse
# vector under the field's bm25 name (content → the body's vectors, else meta_<slug>_*). Kept beside
# the read port (the read-side capability) so no search node ever learns a vector name; the retrieve
# node hands its targets to the port and stays store-agnostic. A metadata lexical vector is queried
# in the encoding it was INDEXED with: the local BM25 query when the vector is BM25-declared
# (``bm25_vectors``, read from the live collection), else the embedder's sparse query (legacy).

# ====== Standard Library Imports ======
from collections.abc import Collection

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from shared_libs.public_models.embed import SparseVector

# ====== Internal Project Imports ======
from shared_libs.public_models.search import CONTENT_FIELD, EncodedQuery, SearchTarget
from shared_libs.services.db.qdrant import SparseVec, VectorNames


class TargetVectorResolver:
    """Static resolver of search targets to the named query-vector dicts the store search consumes."""

    logger = loggerplusplus.bind(identifier="TargetVectorResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TargetVectorResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def __dense_name(field: str) -> str:
        """Resolve a target field to its dense vector name (content body vs. metadata field)."""
        return (
            VectorNames.CONTENT_DENSE if field == CONTENT_FIELD else VectorNames.field_dense(field)
        )

    @staticmethod
    def __sparse_name(field: str) -> str:
        """Resolve a target field to its sparse (BM25) vector name (content body vs. metadata field)."""
        return (
            VectorNames.CONTENT_SPARSE
            if field == CONTENT_FIELD
            else VectorNames.field_sparse(field)
        )

    @staticmethod
    def __sparse_query(
        encoded: EncodedQuery, name: str, bm25_vectors: Collection[str]
    ) -> SparseVector | None:
        """The sparse query for one vector, in that vector's stored encoding (None = nothing)."""
        if name in bm25_vectors:
            meta = encoded.meta_sparse
            return meta if meta is not None and meta.indices else None
        return encoded.sparse

    @classmethod
    def resolve(
        cls,
        encoded: EncodedQuery,
        targets: list[SearchTarget],
        bm25_vectors: Collection[str] = frozenset(),
    ) -> tuple[dict, dict | None]:
        """
        Resolve the requested targets into the named-vector dicts the store search consumes.

        The SAME query vectors are named per target: a semantic target adds the query's dense vector
        under the field's dense name, a lexical target adds its sparse vector under the field's bm25
        name.

        Args:
            encoded (EncodedQuery): The query's vectors.
            targets (list[SearchTarget]): The fields × modalities to search.
            bm25_vectors (Collection[str]): The collection's BM25-encoded metadata sparse vectors —
                they take ``encoded.meta_sparse``; every other sparse vector ``encoded.sparse``.

        Returns:
            tuple[dict, dict | None]: dense name→vec, sparse name→vec (None if empty).

        Raises:
            ValueError: When no modality resolves to a vector (a caller error the API guards against).
        """
        # 1. Fan the single query vectors out over the requested named vectors.
        dense: dict = {}
        sparse: dict = {}
        for target in targets:
            # A semantic target only queries the dense axis when it actually exists — a degraded
            # encode (embedder busy) leaves ``encoded.dense`` empty, and this naturally drops to a
            # lexical-only retrieval instead of sending an empty dense vector to the store.
            if target.semantic and encoded.dense:
                dense[cls.__dense_name(target.field)] = encoded.dense
            if target.lexical:
                name = cls.__sparse_name(target.field)
                query = cls.__sparse_query(encoded, name, bm25_vectors)
                if query is not None:
                    sparse[name] = SparseVec(indices=query.indices, values=query.values)

        # 2. Defensive guard — a targets list that names no queryable vector is a wiring error.
        if not dense and not sparse:
            raise ValueError("search targets resolved to no dense or sparse vector to query")

        return dense, (sparse or None)

    @classmethod
    def termless_lexical_fields(
        cls,
        encoded: EncodedQuery,
        targets: list[SearchTarget],
        bm25_vectors: Collection[str] = frozenset(),
    ) -> list[str]:
        """
        Name the metadata lexical targets the query has no BM25 term for (stopwords/punctuation only).

        Args:
            encoded (EncodedQuery): The query's vectors.
            targets (list[SearchTarget]): The fields × modalities requested.
            bm25_vectors (Collection[str]): The collection's BM25-encoded metadata sparse vectors.

        Returns:
            list[str]: The BM25 metadata lexical target fields whose query vector is empty, in order.
        """
        # 1. Only a BM25-declared vector is queried with the local term vector; a legacy one is not.
        if encoded.meta_sparse is None or encoded.meta_sparse.indices:
            return []
        return [
            target.field
            for target in targets
            if target.lexical
            and target.field != CONTENT_FIELD
            and cls.__sparse_name(target.field) in bm25_vectors
        ]


__all__ = ["TargetVectorResolver"]
