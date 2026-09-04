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
        """Convert a clean QdrantPoint into a qdrant-client PointStruct (id + vectors + payload)."""
        return models.PointStruct(
            id=point.point_id, vector=QdrantIndexApi.__vector_of(point), payload=point.payload
        )

    @staticmethod
    def _to_point_vectors(point: QdrantPoint) -> models.PointVectors | None:
        """Convert a QdrantPoint into a vectors-only update struct, or None when it has no vectors.

        A point with no vectors at all would emit an empty (invalid) named-vector update, so it is
        skipped by returning None.
        """
        vector = QdrantIndexApi.__vector_of(point)
        return models.PointVectors(id=point.point_id, vector=vector) if vector else None

    @staticmethod
    def __vector_of(point: QdrantPoint) -> dict[str, Any]:
        """Build the qdrant named-vector mapping (dense + sparse) shared by both struct builders."""
        vector: dict[str, Any] = dict(point.dense)
        for vec_name, sparse in point.sparse.items():
            vector[vec_name] = models.SparseVector(indices=sparse.indices, values=sparse.values)
        return vector

    # Qdrant rejects any request whose body exceeds its `max_request_size` (32 MB default) with an
    # immediate 400 + connection reset, so a whole-document write can cross the limit. We flush by
    # ESTIMATED payload bytes (full-precision floats serialize at ~22 bytes each), keeping every
    # request well under the limit. __MAX_PAYLOAD_OPS bounds the metadata-patch path by op count
    # (per-op payloads are tiny, but a collection-wide field can patch tens of thousands of points).
    __MAX_UPSERT_BYTES = 16_000_000
    __BYTES_PER_FLOAT = 22
    __MAX_PAYLOAD_OPS = 2_000

    @staticmethod
    def __point_bytes(point: QdrantPoint) -> int:
        """Rough serialized size of a point, dominated by its float vectors."""
        floats = sum(len(vec) for vec in point.dense.values())
        return floats * QdrantIndexApi.__BYTES_PER_FLOAT + 512

    @staticmethod
    def __batched_by_bytes(
        points: Sequence[QdrantPoint], to_struct: Any
    ) -> Any:
        """Yield byte-bounded batches of converted structs so no single request crosses the limit.

        ``to_struct`` maps a point to its qdrant struct (PointStruct or PointVectors); a None result
        skips the point (and its bytes) — used by the vectors-only path for a point with no vectors.
        """
        batch: list[Any] = []
        batch_bytes = 0
        for point in points:
            struct = to_struct(point)
            if struct is None:
                continue
            size = QdrantIndexApi.__point_bytes(point)
            if batch and batch_bytes + size > QdrantIndexApi.__MAX_UPSERT_BYTES:
                yield batch
                batch, batch_bytes = [], 0
            batch.append(struct)
            batch_bytes += size
        if batch:
            yield batch

    @staticmethod
    async def upsert(client: AsyncQdrantClient, name: str, points: Sequence[QdrantPoint]) -> None:
        """Upsert points (id = chunk id) — a matching id overwrites in place. Re-ingest mints NEW
        chunk ids, so its idempotency comes from the facade's prior delete-by-document, not here."""
        # Byte-bounded batches so no single request exceeds Qdrant's limit (empty input → no batch).
        for batch in QdrantIndexApi.__batched_by_bytes(points, QdrantIndexApi._to_struct):
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
        # A collection-wide generated field patches every point — chunk the operations so one giant
        # batch_update_points request can't cross Qdrant's body limit on a large collection.
        operations = [
            models.SetPayloadOperation(
                set_payload=models.SetPayload(payload=payload, points=[point_id])
            )
            for point_id, payload in payloads.items()
        ]
        cap = QdrantIndexApi.__MAX_PAYLOAD_OPS
        for start in range(0, len(operations), cap):
            await client.batch_update_points(
                collection_name=name, update_operations=operations[start : start + cap]
            )

    @staticmethod
    async def update_vectors(
        client: AsyncQdrantClient, name: str, points: Sequence[QdrantPoint]
    ) -> None:
        """
        Update ONLY the provided named vectors on existing points — the post-hoc path for
        SEMANTIC/LEXICAL generated fields (the content vectors are left untouched).

        The named vector must exist in the collection schema (declare the generated field before
        the first indexing); adding a NEW named vector to an existing collection needs a reindex.

        Batched by estimated bytes exactly like ``upsert``: a whole large document's meta vectors in
        one request would cross Qdrant's body limit and 400, silently breaking the meta-vector sync
        at ingest time and aborting the backfill loop mid-collection.
        """
        for batch in QdrantIndexApi.__batched_by_bytes(points, QdrantIndexApi._to_point_vectors):
            await client.update_vectors(collection_name=name, points=batch)

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

    @staticmethod
    async def delete_by_documents(
        client: AsyncQdrantClient, name: str, document_ids: Sequence[uuid.UUID]
    ) -> None:
        """
        Delete every point of a SET of documents in one filtered delete (the bulk-delete path).

        Uses a single ``MatchAny`` over the document_id payload so a mass delete is one Qdrant call
        rather than one per document. The missing-collection guard mirrors the single-document
        variant: a filtered delete on a never-embedded collection 404s, so absence = nothing to do.

        Args:
            client (AsyncQdrantClient): The raw Qdrant client.
            name (str): The collection's Qdrant collection name.
            document_ids (Sequence[uuid.UUID]): The documents whose points are purged.
        """
        if not document_ids or not await client.collection_exists(name):
            return
        await client.delete(
            collection_name=name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key=DOCUMENT_ID_KEY,
                        match=models.MatchAny(any=[str(doc_id) for doc_id in document_ids]),
                    )
                ]
            ),
        )


__all__ = ["QdrantIndexApi"]
