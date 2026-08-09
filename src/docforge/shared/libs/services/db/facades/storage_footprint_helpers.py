# ====== Code Summary ======
# StorageFootprintHelpers — the pure byte arithmetic behind the footprint facade, isolated so the
# facade reads as orchestration and the formulas are unit-testable on their own. It turns a Qdrant
# point count + the sampled shape (dense dim, avg sparse length, avg payload size) into dense/sparse/
# payload byte estimates, and folds the flat (bucket → bytes) Postgres roll-up into a typed model.

# ====== Local Project Imports ======
from .storage_footprint_payloads import PostgresFootprint, QdrantFootprint

# float32 dense component; a sparse entry is an int32 index paired with a float32 value.
_DENSE_COMPONENT_BYTES = 4
_SPARSE_ENTRY_BYTES = 8


class StorageFootprintHelpers:
    """Static byte-estimation formulas shared by the storage-footprint facade."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "StorageFootprintHelpers is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def dense_bytes(points_by_vector: dict[str, int], dense_dims: dict[str, int]) -> int:
        """
        Sum the on-disk dense bytes, each named vector weighted by its OWN carrier point count.

        ``content_dense`` rides every point; a ``meta_<slug>_dense`` rides only the points of the
        documents that populate its field — so a per-vector carrier count is required, never the
        collection total. Bytes are on-disk float32 (``× 4``); the int8 scalar-quantized copy Qdrant
        keeps resident in RAM (+1 B/dim) is intentionally EXCLUDED — this measures disk, not RAM.

        Args:
            points_by_vector (dict[str, int]): Named dense vector → the number of points carrying it.
            dense_dims (dict[str, int]): Named dense vector → its declared dimension.

        Returns:
            int: The summed on-disk dense bytes.
        """
        # 1. Only DECLARED vectors contribute; a carrier for an undeclared vector (reindex-pending)
        #    holds no bytes yet. Each vector: its carriers × its dim × 4 (float32).
        return sum(
            int(points_by_vector.get(name, 0) * dim * _DENSE_COMPONENT_BYTES)
            for name, dim in dense_dims.items()
        )

    @staticmethod
    def qdrant_footprint(
        points: int,
        dense_bytes: int,
        avg_sparse_entries: float,
        avg_payload_bytes: float,
    ) -> QdrantFootprint:
        """
        Assemble a point set's vector-store footprint from its dense bytes + sampled sparse/payload.

        Args:
            points (int): The number of points (collection total, or a document's points).
            dense_bytes (int): Pre-summed on-disk dense bytes (see :meth:`dense_bytes`).
            avg_sparse_entries (float): Mean non-zero entries per point across sparse vectors.
            avg_payload_bytes (float): Mean payload JSON size per point.

        Returns:
            QdrantFootprint: The dense/sparse/payload estimate and their total.
        """
        # 1. Sparse + payload scale linearly with the point count (index overhead excluded).
        sparse = int(points * avg_sparse_entries * _SPARSE_ENTRY_BYTES)
        payload = int(points * avg_payload_bytes)

        # 2. Bundle the components with their sum (dense already weighted per named vector).
        return QdrantFootprint(
            points=points,
            dense_bytes=dense_bytes,
            sparse_bytes=sparse,
            payload_bytes=payload,
            total_bytes=dense_bytes + sparse + payload,
        )

    @staticmethod
    def postgres_footprint(buckets: dict[str, int]) -> PostgresFootprint:
        """
        Fold a flat (bucket → bytes) mapping into the typed Postgres footprint (missing bucket = 0).

        Args:
            buckets (dict[str, int]): The per-bucket byte sums (``documents``, ``ir_blocks``,
                ``enrichment``, ``chunks``, ``metadata``, ``observability``).

        Returns:
            PostgresFootprint: The typed model with a recomputed total.
        """
        # 1. Read each named bucket defensively — an absent bucket contributes zero.
        documents = buckets.get("documents", 0)
        ir_blocks = buckets.get("ir_blocks", 0)
        enrichment = buckets.get("enrichment", 0)
        chunks = buckets.get("chunks", 0)
        metadata = buckets.get("metadata", 0)
        observability = buckets.get("observability", 0)

        # 2. The total is the honest sum of every bucket (never a stored, driftable number).
        return PostgresFootprint(
            documents_bytes=documents,
            ir_blocks_bytes=ir_blocks,
            enrichment_bytes=enrichment,
            chunks_bytes=chunks,
            metadata_bytes=metadata,
            observability_bytes=observability,
            total_bytes=documents + ir_blocks + enrichment + chunks + metadata + observability,
        )


__all__ = ["StorageFootprintHelpers"]
