# ====== Code Summary ======
# Static helpers for Qdrant multi-vector point upsert: builds one PointStruct per
# chunk (attaching only non-None named dense/sparse vectors) and batch-upserts them.
# Separated from payload-mutation helpers so each file owns a single concern.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, SparseVector


class QdrantUpsertHelpers:
    """
    Static helpers for upserting multi-vector points into Qdrant.

    Encapsulates PointStruct construction (attaching only the named vectors that
    carry a value) and the batched upsert call.  All methods take the live
    ``AsyncQdrantClient`` as an explicit argument so the class holds no state.
    """

    logger = loggerplusplus.bind(identifier="QdrantUpsertHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only class."""
        raise TypeError("QdrantUpsertHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def upsert_points(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        chunk_ids: list[str],
        dense_by_vector: dict[str, list[list[float] | None]],
        sparse_by_vector: dict[str, list[dict[int, float] | None]],
        payloads: list[dict[str, Any]],
    ) -> int:
        """
        Upsert points carrying multiple named dense + sparse vectors (spec §7.2).

        Idempotent by chunk_id. Per chunk, only vectors with a non-None value are attached —
        a chunk lacking a value for a field (e.g. an empty custom field) simply omits that
        named vector, which Qdrant supports.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.
            chunk_ids (list[str]): UUID strings used as point IDs.
            dense_by_vector (dict): vector_name → list of dense vectors (one per chunk; None to skip).
            sparse_by_vector (dict): vector_name → list of BM25 maps (one per chunk; None to skip).
            payloads (list[dict]): Filterable payload per chunk.

        Returns:
            int: Number of points upserted.
        """
        if not chunk_ids:
            return 0
        n = len(chunk_ids)

        # 1. Build one PointStruct per chunk, attaching only non-None named vectors
        points = [
            cls._build_point(
                chunk_id=chunk_id,
                index=i,
                dense_by_vector=dense_by_vector,
                sparse_by_vector=sparse_by_vector,
                payload=payloads[i],
            )
            for i, chunk_id in enumerate(chunk_ids)
        ]

        # 2. Batch upsert
        await client.upsert(collection_name=collection_name, points=points)
        cls.logger.debug(f"Qdrant: upserted {n} multi-vector point(s) → {collection_name!r}")
        return n

    @staticmethod
    def _build_point(
        chunk_id: str,
        index: int,
        dense_by_vector: dict[str, list[list[float] | None]],
        sparse_by_vector: dict[str, list[dict[int, float] | None]],
        payload: dict[str, Any],
    ) -> PointStruct:
        """
        Build a single multi-vector PointStruct for one chunk.

        Only named vectors that carry a value at ``index`` are attached; missing or
        None entries are skipped (Qdrant allows points to omit named vectors).

        Args:
            chunk_id (str): UUID string used as the point ID.
            index (int): Position of this chunk within the per-vector value lists.
            dense_by_vector (dict): vector_name → list of dense vectors.
            sparse_by_vector (dict): vector_name → list of BM25 maps.
            payload (dict): Filterable payload for this chunk.

        Returns:
            PointStruct: The constructed point.
        """
        vector: dict[str, Any] = {}

        # 1. Dense named vectors (content + per semantic field)
        for vname, vecs in dense_by_vector.items():
            v = vecs[index] if index < len(vecs) else None
            if v is not None:
                vector[vname] = v

        # 2. Sparse named vectors (content + per lexical field)
        for vname, maps in sparse_by_vector.items():
            sp = maps[index] if index < len(maps) else None
            if sp:
                vector[vname] = SparseVector(indices=list(sp.keys()), values=list(sp.values()))

        return PointStruct(id=chunk_id, vector=vector, payload=payload)
