# ====== Code Summary ======
# QdrantIndexApi — the WRITE operations of the vector store: upsert points (id = chunk id), delete a
# document's points (the re-ingest cleanup — the ingestion facade deletes-by-document before it
# upserts, because each run remints chunk ids so a plain upsert would NOT overwrite the previous
# run's points), and the two POST-HOC metagen writes on EXISTING points — patch payload values (a
# filterable generated field) and update named vectors (a semantic/lexical generated field) — so new
# chunk metadata lands in the index without re-embedding the content. Converts the clean QdrantPoint
# into qdrant structs; nothing leaks up.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models

# ====== Local Project Imports ======
from ..vectors import DOCUMENT_ID_KEY, QdrantPoint


class QdrantIndexApi:
    """Static write operations (upsert / delete) for the vector store."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantIndexApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def _to_struct(point: QdrantPoint) -> models.PointStruct:
        """Convert a clean QdrantPoint into a qdrant-client PointStruct."""
        vector: dict[str, Any] = dict(point.dense)
        for name, sparse in point.sparse.items():
            vector[name] = models.SparseVector(indices=sparse.indices, values=sparse.values)
        return models.PointStruct(id=point.point_id, vector=vector, payload=point.payload)

    # Qdrant rejects any request whose body exceeds its `max_request_size` (32 MB default) with an
    # immediate 400 + connection reset, so a whole-document upsert can cross the limit. We flush by
    # ESTIMATED payload bytes (full-precision floats serialize at ~22 bytes each), keeping every
    # request well under the limit.
    __MAX_UPSERT_BYTES = 16_000_000
    __BYTES_PER_FLOAT = 22

    @staticmethod
    def __point_bytes(point: QdrantPoint) -> int:
        """Rough serialized size of a point, dominated by its float vectors."""
        floats = sum(len(vec) for vec in point.dense.values())
        return floats * QdrantIndexApi.__BYTES_PER_FLOAT + 512

    @staticmethod
    async def upsert(client: AsyncQdrantClient, name: str, points: Sequence[QdrantPoint]) -> None:
        """Upsert points (id = chunk id) — a matching id overwrites in place. Re-ingest mints NEW
        chunk ids, so its idempotency comes from the facade's prior delete-by-document, not here."""
        if not points:
            return
        # 1. Pack points into byte-bounded batches so no single request exceeds Qdrant's limit.
        batch: list[models.PointStruct] = []
        batch_bytes = 0
        for point in points:
            size = QdrantIndexApi.__point_bytes(point)
            if batch and batch_bytes + size > QdrantIndexApi.__MAX_UPSERT_BYTES:
                await client.upsert(collection_name=name, points=batch)
                batch, batch_bytes = [], 0
            batch.append(QdrantIndexApi._to_struct(point))
            batch_bytes += size
        # 2. Flush the final batch (always at least one point).
        if batch:
            await client.upsert(collection_name=name, points=batch)

    @staticmethod
    async def set_payload(
        client: AsyncQdrantClient, name: str, payloads: Mapping[str, dict[str, Any]]
    ) -> None:
        """
        Patch payload keys on existing points — the post-hoc path for FILTERABLE generated fields.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            payloads (Mapping[str, dict]): point id → the payload keys to set/overwrite (merged
                into the existing payload; other keys are untouched).
        """
        # One batched request — a collection-wide generated field patches thousands of points.
        operations = [
            models.SetPayloadOperation(
                set_payload=models.SetPayload(payload=payload, points=[point_id])
            )
            for point_id, payload in payloads.items()
        ]
        if operations:
            await client.batch_update_points(collection_name=name, update_operations=operations)

    @staticmethod
    async def update_vectors(
        client: AsyncQdrantClient, name: str, points: Sequence[QdrantPoint]
    ) -> None:
        """
        Update ONLY the provided named vectors on existing points — the post-hoc path for
        SEMANTIC/LEXICAL generated fields (the content vectors are left untouched).

        The named vector must exist in the collection schema (declare the generated field before
        the first indexing); adding a NEW named vector to an existing collection needs a reindex.
        """
        structs: list[models.PointVectors] = []
        for point in points:
            vector: dict[str, Any] = dict(point.dense)
            for vec_name, sparse in point.sparse.items():
                vector[vec_name] = models.SparseVector(indices=sparse.indices, values=sparse.values)
            # A point with no vectors at all would emit an empty (invalid) update — skip it.
            if vector:
                structs.append(models.PointVectors(id=point.point_id, vector=vector))
        if structs:
            await client.update_vectors(collection_name=name, points=structs)

    @staticmethod
    async def delete_by_document(
        client: AsyncQdrantClient, name: str, document_id: uuid.UUID
    ) -> None:
        """Delete every point of a document (filter on the document_id payload)."""
        # A document that never reached the embed stage (parse/enrich failed) has no points AND no
        # collection yet — Qdrant answers a filtered delete on a missing collection with a 404, not
        # an empty result. Treat "collection absent" as "nothing to delete" so deleting/reingesting
        # such a document is idempotent instead of surfacing a spurious 500.
        if not await client.collection_exists(name):
            return
        await client.delete(
            collection_name=name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key=DOCUMENT_ID_KEY, match=models.MatchValue(value=str(document_id))
                    )
                ]
            ),
        )


__all__ = ["QdrantIndexApi"]
