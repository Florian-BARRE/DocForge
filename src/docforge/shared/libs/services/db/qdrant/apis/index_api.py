# ====== Code Summary ======
# QdrantIndexApi — the WRITE operations of the vector store: upsert points (id = chunk id), delete a
# document's points (document delete), delete only a document's STALE points (the re-ingest cleanup —
# point ids are deterministic per (document, chunk ordinal), so the ingestion facade upserts FIRST,
# overwriting in place, then drops the ids the new run no longer produced), and the two POST-HOC metagen writes on EXISTING points — patch payload values (a
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
from .alias_api import QdrantAliasApi


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
    def __batched_by_bytes(points: Sequence[QdrantPoint], to_struct: Any) -> Any:
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
        """Upsert points (id = chunk id) — a matching id overwrites in place. Point ids are
        deterministic per (document, ordinal); the facade's post-upsert stale purge drops the rest."""
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
        if not await QdrantAliasApi.resolve_or_adopt(client, name):
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
    async def delete_stale_for_document(
        client: AsyncQdrantClient, name: str, document_id: uuid.UUID, keep_ids: Sequence[str]
    ) -> None:
        """
        Delete a document's points whose id is NOT in ``keep_ids`` (the post-upsert stale purge).

        Run AFTER the fresh points were upserted: the document is never left without points, even if
        this purge (or the upsert before it) fails. Guards the missing-collection case like
        ``delete_by_document``.

        Args:
            client (AsyncQdrantClient): The raw Qdrant client.
            name (str): The collection's Qdrant collection name.
            document_id (uuid.UUID): The document whose leftover points are purged.
            keep_ids (Sequence[str]): The point ids the current run produced (kept).
        """
        if not await QdrantAliasApi.resolve_or_adopt(client, name):
            return
        await client.delete(
            collection_name=name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key=DOCUMENT_ID_KEY, match=models.MatchValue(value=str(document_id))
                    )
                ],
                must_not=[models.HasIdCondition(has_id=list(keep_ids))] if keep_ids else None,
            ),
        )

    @staticmethod
    async def delete_payload(
        client: AsyncQdrantClient, name: str, keys: list[str], document_id: uuid.UUID
    ) -> None:
        """
        Delete specific payload keys from every point of a document (the metadata-clear path).

        The inverse of ``set_payload``: when a FILTERABLE document-scope field is cleared, its
        denormalised payload key must be removed from each of the document's chunk points so the old
        value stops matching a ``filters={field: value}`` search. Guards the missing-collection case
        exactly like ``delete_by_document`` (a document that never reached embed has no collection yet,
        and a filtered op on a missing collection 404s) and no-ops on an empty key list.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            keys (list[str]): The payload keys to delete (the cleared fields' names).
            document_id (uuid.UUID): The document whose points are patched.
        """
        if not keys or not await QdrantAliasApi.resolve_or_adopt(client, name):
            return
        await client.delete_payload(
            collection_name=name,
            keys=keys,
            points=models.Filter(
                must=[
                    models.FieldCondition(
                        key=DOCUMENT_ID_KEY, match=models.MatchValue(value=str(document_id))
                    )
                ]
            ),
        )

    @staticmethod
    async def delete_vectors(
        client: AsyncQdrantClient, name: str, vector_names: list[str], document_id: uuid.UUID
    ) -> None:
        """
        Delete named vectors from every point of a document (the metadata-clear path).

        The inverse of ``update_vectors``: when a SEMANTIC/LEXICAL document-scope field is cleared, its
        ``meta_<slug>_dense`` / ``meta_<slug>_bm25`` named vector must be dropped from each of the
        document's chunk points so the old value stops contributing to a metadata search. The content
        vectors (``content_dense`` / ``content_bm25``) are never named here, so they are untouched.
        Guards the missing-collection case like ``delete_by_document`` and no-ops on an empty list.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            vector_names (list[str]): The named vectors to delete (the cleared fields' meta vectors).
            document_id (uuid.UUID): The document whose points are patched.
        """
        if not vector_names or not await QdrantAliasApi.resolve_or_adopt(client, name):
            return
        await client.delete_vectors(
            collection_name=name,
            vectors=vector_names,
            points=models.Filter(
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
        if not document_ids or not await QdrantAliasApi.resolve_or_adopt(client, name):
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
