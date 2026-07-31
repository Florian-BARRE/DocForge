# ====== Code Summary ======
# QdrantVectorSchema — derives a Qdrant collection's named-vector layout from the collection's
# metadata schema. Always: one dense (content_dense) + one sparse (content_bm25) for the chunk body.
# Then one dense vector per SEMANTIC field and one sparse vector per LEXICAL field. This is what
# `ensure_collection` builds the Qdrant collection from, so the vector space mirrors the contract.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import models

# ====== Local Project Imports ======
from .names import VectorNames


class QdrantVectorSchema:
    """Static builder of a collection's dense/sparse named-vector configuration."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantVectorSchema is a static-only class and cannot be instantiated.")

    @staticmethod
    def dense_config(
        dense_dim: int, semantic_fields: Sequence[str]
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
        picks it up via an online ``update_collection`` reindex (no drop).
        """
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
    def sparse_config(lexical_fields: Sequence[str]) -> dict[str, models.SparseVectorParams]:
        """Named sparse (BM25) vectors: the chunk body and one per lexical metadata field."""
        config = {
            VectorNames.CONTENT_SPARSE: models.SparseVectorParams(),
        }
        for field_name in lexical_fields:
            config[VectorNames.field_sparse(field_name)] = models.SparseVectorParams()
        return config


__all__ = ["QdrantVectorSchema"]
