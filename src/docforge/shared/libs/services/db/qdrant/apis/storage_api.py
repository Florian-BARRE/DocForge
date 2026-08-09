# ====== Code Summary ======
# QdrantStorageApi — the read-only vector-store side of a collection's footprint. It profiles a live
# Qdrant collection WITHOUT scanning every point: the collection-info API yields the declared dense
# named-vector dimensions + sparse names, an EXACT count yields the total point tally, the facet API
# yields the per-document point counts in ONE call (never a scroll of all points), and a small scroll
# SAMPLE yields the average sparse-vector length + payload JSON size the caller multiplies out. A
# collection that was never embedded (no Qdrant space yet) profiles as None — the caller reports 0.

# ====== Standard Library Imports ======
import json
from dataclasses import dataclass, field

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient

# ====== Local Project Imports ======
from ..vectors import DOCUMENT_ID_KEY


@dataclass(slots=True)
class QdrantProfile:
    """The sampled, count-based profile of a collection's vector store — the estimate's raw inputs.

    Attributes:
        total_points (int): Exact point count across the whole collection.
        dense_dims (dict[str, int]): Declared dense named vector → its dimension. ``content_dense``
            rides EVERY point; a ``meta_<slug>_dense`` rides only the points (chunks) of documents
            that populate that semantic field — so the caller weights each vector by its own carrier
            count, never by the total (which would over-count sparsely-populated metadata vectors).
        avg_sparse_entries (float): Mean non-zero entries per point, summed over sparse named vectors.
        avg_payload_bytes (float): Mean JSON size of a point's payload (bytes).
        per_document_points (dict[str, int]): Point count per ``document_id`` payload value (facet).
    """

    total_points: int
    dense_dims: dict[str, int]
    avg_sparse_entries: float
    avg_payload_bytes: float
    per_document_points: dict[str, int] = field(default_factory=dict)


class QdrantStorageApi:
    """Static, read-only profiling of a collection's vector store for footprint estimation."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantStorageApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def __dense_dims(vectors: object) -> dict[str, int]:
        """Map each declared dense named vector to its dimension ({} when the space is empty)."""
        # DocForge always uses NAMED vectors, so params.vectors is a name → VectorParams mapping.
        if not isinstance(vectors, dict):
            return {}
        return {name: int(params.size) for name, params in vectors.items()}

    @staticmethod
    def __sample_averages(points: list) -> tuple[float, float]:
        """Average sparse-entry count and payload JSON size over a scroll sample (0.0 when empty)."""
        # 1. No sample → no signal; the caller multiplies zeros, a safe estimate for an empty space.
        if not points:
            return 0.0, 0.0
        # 2. Fold each sampled point: payload JSON length + summed sparse index count across vectors.
        sparse_sum = 0
        payload_sum = 0
        for point in points:
            payload_sum += len(json.dumps(point.payload or {}, default=str))
            vectors = point.vector or {}
            if isinstance(vectors, dict):
                for vector in vectors.values():
                    # A sparse vector carries `indices`; a dense one is a plain list (skipped here).
                    indices = getattr(vector, "indices", None)
                    if indices is not None:
                        sparse_sum += len(indices)
        return sparse_sum / len(points), payload_sum / len(points)

    @classmethod
    async def profile(
        cls,
        client: AsyncQdrantClient,
        name: str,
        *,
        facet_limit: int,
        sample_size: int = 32,
    ) -> QdrantProfile | None:
        """
        Profile a collection's vector store for footprint estimation (None when it has no space yet).

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            facet_limit (int): Upper bound on distinct documents to return counts for (≥ doc count).
            sample_size (int): How many points to scroll for the sparse/payload averages.

        Returns:
            QdrantProfile | None: The profile, or None when the collection does not exist yet.
        """
        # 1. A collection provisions its space lazily at first embed — absent means footprint 0.
        if not await client.collection_exists(name):
            return None

        # 2. Declared vector space: per-vector dense dimensions (each weighted by its OWN carrier
        #    count downstream — content on every point, a meta vector only on its field's documents).
        info = await client.get_collection(name)
        dense_dims = cls.__dense_dims(info.config.params.vectors)

        # 3. Exact total tally + per-document counts (one facet call, never an all-points scroll).
        total_points = (await client.count(collection_name=name, exact=True)).count
        per_document: dict[str, int] = {}
        facet = await client.facet(
            collection_name=name, key=DOCUMENT_ID_KEY, limit=max(facet_limit, 1)
        )
        for hit in facet.hits:
            per_document[str(hit.value)] = int(hit.count)

        # 4. Sample a handful of points for the sparse-length + payload-size averages.
        avg_sparse, avg_payload = 0.0, 0.0
        if total_points:
            points, _ = await client.scroll(
                collection_name=name,
                limit=sample_size,
                with_payload=True,
                with_vectors=True,
            )
            avg_sparse, avg_payload = cls.__sample_averages(points)

        return QdrantProfile(
            total_points=total_points,
            dense_dims=dense_dims,
            avg_sparse_entries=avg_sparse,
            avg_payload_bytes=avg_payload,
            per_document_points=per_document,
        )


__all__ = ["QdrantStorageApi", "QdrantProfile"]
