# ====== Code Summary ======
# Static helpers for Qdrant point and payload operations:
# upsert point building, payload patching, vector updates, and point deletion.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    PointIdsList,
    PointStruct,
    PointVectors,
    SparseVector,
)


class QdrantPointHelpers:
    """
    Static helpers for Qdrant point and payload operations.

    Encapsulates upsert point construction, payload patching, named vector
    updates, and point deletion.  All methods take the live
    ``AsyncQdrantClient`` as an explicit argument so that this class carries
    no instance state of its own.
    """

    logger = loggerplusplus.bind(identifier="QdrantPointHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only class."""
        raise TypeError("QdrantPointHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def delete_points(
        cls, client: AsyncQdrantClient, collection_name: str, point_ids: list[str]
    ) -> int:
        """
        Delete specific points by id (idempotent; missing ids are ignored by Qdrant).

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.
            point_ids (list[str]): Point ids (chunk ids) to delete.

        Returns:
            int: Number of point ids submitted for deletion (0 if list is empty or
                 the collection does not exist).
        """
        # 1. Short-circuit on empty input or missing collection
        if not point_ids:
            return 0
        if not await client.collection_exists(collection_name):
            return 0

        # 2. Delete and report
        await client.delete(collection_name=collection_name, points_selector=PointIdsList(points=point_ids))
        cls.logger.debug(f"Qdrant: deleted {len(point_ids)} point(s) → {collection_name!r}")
        return len(point_ids)

    @classmethod
    async def set_points_payload(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        point_ids: list[str],
        payload: dict[str, Any],
    ) -> None:
        """
        Merge a payload patch into the given points (existing keys overwritten).

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.
            point_ids (list[str]): Points to update.
            payload (dict): Key-value pairs to set on each point.
        """
        if not point_ids or not payload:
            return
        await client.set_payload(collection_name=collection_name, payload=payload, points=point_ids)
        cls.logger.debug(f"Qdrant: set payload {list(payload)} on {len(point_ids)} point(s)")

    @classmethod
    async def delete_points_payload_keys(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        point_ids: list[str],
        keys: list[str],
    ) -> None:
        """
        Remove specific payload keys from the given points (for cleared metadata fields).

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.
            point_ids (list[str]): Points to update.
            keys (list[str]): Payload key names to remove.
        """
        if not point_ids or not keys:
            return
        await client.delete_payload(collection_name=collection_name, keys=keys, points=point_ids)
        cls.logger.debug(f"Qdrant: removed payload keys {keys} from {len(point_ids)} point(s)")

    @classmethod
    async def update_points_named_vector(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        point_ids: list[str],
        vector_name: str,
        *,
        dense: list[float] | None = None,
        sparse: dict[int, float] | None = None,
    ) -> None:
        """
        Set one named vector to the same value on every given point.

        Document-level metadata fields embed to the same vector for all of a document's chunks,
        so a single embedding is broadcast across its points.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.
            point_ids (list[str]): Points to update.
            vector_name (str): Named vector key (e.g. ``meta_dossier_dense``).
            dense (list[float] | None): Dense vector value, or None.
            sparse (dict[int, float] | None): Sparse BM25 map, or None.
        """
        if not point_ids or (dense is None and not sparse):
            return

        # 1. Build the vector value — dense takes precedence over sparse
        value: Any = dense if dense is not None else SparseVector(
            indices=list(sparse.keys()), values=list(sparse.values())
        )

        # 2. Broadcast the same vector to all target points
        await client.update_vectors(
            collection_name=collection_name,
            points=[PointVectors(id=pid, vector={vector_name: value}) for pid in point_ids],
        )
        cls.logger.debug(f"Qdrant: updated vector {vector_name!r} on {len(point_ids)} point(s)")

    @classmethod
    async def delete_points_named_vectors(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        point_ids: list[str],
        vector_names: list[str],
    ) -> None:
        """
        Delete named vectors from the given points (for cleared searchable fields).

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.
            point_ids (list[str]): Points to update.
            vector_names (list[str]): Named vector keys to remove.
        """
        if not point_ids or not vector_names:
            return
        await client.delete_vectors(
            collection_name=collection_name, vectors=vector_names, points=point_ids
        )
        cls.logger.debug(f"Qdrant: deleted vectors {vector_names} from {len(point_ids)} point(s)")

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
        points: list[PointStruct] = []
        for i, chunk_id in enumerate(chunk_ids):
            vector: dict[str, Any] = {}

            # 1a. Dense named vectors (content + per semantic field)
            for vname, vecs in dense_by_vector.items():
                v = vecs[i] if i < len(vecs) else None
                if v is not None:
                    vector[vname] = v

            # 1b. Sparse named vectors (content + per lexical field)
            for vname, maps in sparse_by_vector.items():
                sp = maps[i] if i < len(maps) else None
                if sp:
                    vector[vname] = SparseVector(indices=list(sp.keys()), values=list(sp.values()))

            points.append(PointStruct(id=chunk_id, vector=vector, payload=payloads[i]))

        # 2. Batch upsert
        await client.upsert(collection_name=collection_name, points=points)
        cls.logger.debug(f"Qdrant: upserted {n} multi-vector point(s) → {collection_name!r}")
        return n
