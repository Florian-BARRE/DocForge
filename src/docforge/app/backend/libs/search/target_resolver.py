# ====== Code Summary ======
# TargetVectorResolver — the ONE place that knows how a SearchTarget maps to a Qdrant named vector.
# It fans the query's single dense/sparse vectors out over the requested targets: a semantic target
# names the query's dense vector under the field's dense name, a lexical target names its sparse
# vector under the field's bm25 name (content → the body's vectors, else meta_<slug>_*). Kept beside
# the read port (the read-side capability) so no search node ever learns a vector name; the retrieve
# node hands its targets to the port and stays store-agnostic.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

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

    @classmethod
    def resolve(
        cls, encoded: EncodedQuery, targets: list[SearchTarget]
    ) -> tuple[dict, dict | None]:
        """
        Resolve the requested targets into the named-vector dicts the store search consumes.

        The SAME query vectors are named per target: a semantic target adds the query's dense vector
        under the field's dense name, a lexical target adds its sparse vector under the field's bm25
        name.

        Args:
            encoded (EncodedQuery): The query's vectors.
            targets (list[SearchTarget]): The fields × modalities to search.

        Returns:
            tuple[dict, dict | None]: dense name→vec, sparse name→vec (None if empty).

        Raises:
            ValueError: When no modality resolves to a vector (a caller error the API guards against).
        """
        # 1. Fan the single query vectors out over the requested named vectors.
        dense: dict = {}
        sparse: dict = {}
        for target in targets:
            if target.semantic:
                dense[cls.__dense_name(target.field)] = encoded.dense
            if target.lexical and encoded.sparse is not None:
                sparse[cls.__sparse_name(target.field)] = SparseVec(
                    indices=encoded.sparse.indices, values=encoded.sparse.values
                )

        # 2. Defensive guard — a targets list that names no queryable vector is a wiring error.
        if not dense and not sparse:
            raise ValueError("search targets resolved to no dense or sparse vector to query")

        return dense, (sparse or None)


__all__ = ["TargetVectorResolver"]
