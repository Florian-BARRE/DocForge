# ====== Code Summary ======
# QdrantVectorSchema — derives a Qdrant collection's named-vector layout from the collection's
# metadata schema AND its embedder's VectorLayout (read off the embed config, never guessed): a dense
# provider → content_dense + one dense vector per SEMANTIC field; a sparse provider → content_bm25 +
# one sparse vector per LEXICAL field. Every sparse vector carries ``modifier=IDF`` iff the sparse
# provider emits term frequencies (bm25_local); learned sparse weights (bge_server) carry none. A live
# sparse vector whose modifier differs from what the config requires holds another encoder's vectors
# (``modifier_mismatch``) and is reported for an index rebuild — never queried or written as is.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import models

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout

# ====== Local Project Imports ======
from .names import VectorNames


class QdrantVectorSchema:
    """Static builder of a collection's dense/sparse named-vector configuration."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantVectorSchema is a static-only class and cannot be instantiated.")

    @staticmethod
    def dense_config(
        dense_dim: int, semantic_fields: Sequence[str], layout: VectorLayout | None = None
    ) -> dict[str, models.VectorParams]:
        """
        Named dense vectors: the chunk body plus one per semantic metadata field.

        RAM mitigation: dense vectors default to full float32 resident in RAM (1024 dims × 4 B ≈
        4 KiB/vector → the store's dominant, unbounded-with-corpus memory cost). Instead:
          - ``on_disk=True`` keeps the original float32 vectors mmap'd on disk (not in RAM);
          - int8 scalar quantization with ``always_ram=True`` keeps a 4×-smaller (1 B/dim) quantized
            copy in RAM for the HNSW traversal, and Qdrant rescores the top candidates from the
            on-disk float32 — so recall is largely recovered despite the lossy quantization.
        Net ~4× less dense-vector RAM. Applies to newly created collections; an existing collection
        picks it up via an online ``update_collection`` reindex (no drop). No dense provider (a
        sparse-only layout) → no dense vector at all.
        """
        if layout is not None and not layout.dense:
            return {}
        params = models.VectorParams(
            size=dense_dim,
            distance=models.Distance.COSINE,
            on_disk=True,
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)
            ),
        )
        config = {VectorNames.CONTENT_DENSE: params}
        for field_name in semantic_fields:
            config[VectorNames.field_dense(field_name)] = params
        return config

    @staticmethod
    def sparse_config(
        lexical_fields: Sequence[str], layout: VectorLayout | None = None
    ) -> dict[str, models.SparseVectorParams]:
        """
        Named sparse vectors: the chunk body and one per lexical metadata field (none without a
        sparse provider), every one declared with ``modifier=IDF`` iff the layout says so.

        Args:
            lexical_fields (Sequence[str]): Fields that get a named sparse vector.
            layout (VectorLayout | None): The embedder's layout (None → the legacy dense+sparse,
                no-IDF layout).

        Returns:
            dict[str, SparseVectorParams]: Vector name → params.
        """
        layout = layout or VectorLayout()
        if not layout.sparse:
            return {}
        names = [VectorNames.CONTENT_SPARSE, *(VectorNames.field_sparse(f) for f in lexical_fields)]
        modifier = models.Modifier.IDF if layout.sparse_idf else None
        return {name: models.SparseVectorParams(modifier=modifier) for name in names}

    @staticmethod
    def is_idf(params: models.SparseVectorParams | None) -> bool:
        """Whether a DECLARED sparse vector carries the IDF modifier."""
        return getattr(params, "modifier", None) == models.Modifier.IDF

    @classmethod
    def modifier_mismatch(
        cls, params: models.SparseVectorParams | None, layout: VectorLayout
    ) -> bool:
        """Whether a declared sparse vector's IDF modifier differs from what the layout requires."""
        return cls.is_idf(params) != layout.sparse_idf


__all__ = ["QdrantVectorSchema"]
