# ====== Code Summary ======
# QdrantVectorSchema — derives a Qdrant collection's named-vector layout from the collection's
# metadata schema. Always: one dense (content_dense) + one sparse (content_bm25) for the chunk body.
# Then one dense vector per SEMANTIC field and one sparse vector per LEXICAL field. This is what
# `ensure_collection` builds the Qdrant collection from, so the vector space mirrors the contract.
# The per-field lexical vectors carry ``modifier=IDF``: they hold the local BM25 term frequencies
# (MetaLexicalEncoder, encoding ``bm25_v1``) and Qdrant supplies the IDF. That modifier is ALSO the
# encoding marker — a collection created before it holds BGE-M3 sparse weights in those vectors, and
# every writer/reader tests ``is_bm25_meta`` on the LIVE declared params so index and query never mix
# encoders. A collection switches only by being recreated from this schema (rebuild_index).

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
        """
        Named sparse vectors: the chunk body and one per lexical metadata field.

        The body vector (``content_bm25``) holds the embedder's learned sparse weights as-is (no
        modifier). Each metadata vector holds local BM25 term frequencies, so it is declared with
        ``modifier=IDF`` — Qdrant computes the inverse document frequency over the collection.
        """
        config = {
            VectorNames.CONTENT_SPARSE: models.SparseVectorParams(),
        }
        for field_name in lexical_fields:
            config[VectorNames.field_sparse(field_name)] = models.SparseVectorParams(
                modifier=models.Modifier.IDF
            )
        return config

    @staticmethod
    def is_bm25_meta(name: str, params: models.SparseVectorParams | None) -> bool:
        """
        Whether a DECLARED sparse vector is a metadata vector in the local BM25 encoding.

        The single encoding test: a ``meta_<slug>_bm25`` vector declared with ``modifier=IDF`` was
        created by the current schema and holds MetaLexicalEncoder output; one without it predates
        the switch and holds the embedder's (BGE-M3) sparse weights until the collection is rebuilt.

        Args:
            name (str): The declared sparse vector name.
            params (SparseVectorParams | None): Its declared params, as Qdrant reports them.

        Returns:
            bool: True for a BM25-encoded metadata vector.
        """
        return (
            VectorNames.is_field_sparse(name)
            and params is not None
            and params.modifier == models.Modifier.IDF
        )


__all__ = ["QdrantVectorSchema"]
