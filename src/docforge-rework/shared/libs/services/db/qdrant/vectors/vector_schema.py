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
    def dense_config(dense_dim: int, semantic_fields: Sequence[str]) -> dict[str, models.VectorParams]:
        """Named dense vectors: the chunk body plus one per semantic metadata field."""
        params = models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
        config = {VectorNames.CONTENT_DENSE: params}
        for field_name in semantic_fields:
            config[VectorNames.field_dense(field_name)] = params
        return config

    @staticmethod
    def colbert_config(dim: int) -> dict[str, models.VectorParams]:
        """
        The chunk body's ColBERT multi-vector (MAX_SIM late interaction), content point only.

        Storage mitigation — a ColBERT vector is ~30x the size of one dense vector (one token
        vector per token), so it is pushed on_disk and scalar-quantized to int8; both keep the
        heavy multi-vector out of RAM while the MAX_SIM comparator does the late-interaction score.

        Args:
            dim (int): Dimension of each per-token ColBERT vector.

        Returns:
            dict[str, models.VectorParams]: The single ``content_colbert`` named-vector config.
        """
        return {
            VectorNames.CONTENT_COLBERT: models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
                multivector_config=models.MultiVectorConfig(
                    comparator=models.MultiVectorComparator.MAX_SIM
                ),
                on_disk=True,
                quantization_config=models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(
                        type=models.ScalarType.INT8, always_ram=False
                    )
                ),
            )
        }

    @staticmethod
    def sparse_config(lexical_fields: Sequence[str]) -> dict[str, models.SparseVectorParams]:
        """Named sparse (BM25) vectors: the chunk body, the doc2query questions, and one per
        lexical metadata field."""
        config = {
            VectorNames.CONTENT_SPARSE: models.SparseVectorParams(),
            VectorNames.CONTENT_QUERIES_SPARSE: models.SparseVectorParams(),
        }
        for field_name in lexical_fields:
            config[VectorNames.field_sparse(field_name)] = models.SparseVectorParams()
        return config


__all__ = ["QdrantVectorSchema"]
