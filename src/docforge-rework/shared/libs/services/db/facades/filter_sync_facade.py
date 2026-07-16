# ====== Code Summary ======
# FilterSyncFacade — denormalises a document's FILTERABLE document-scope metadata onto every one of
# its chunk Qdrant points, so a document-level field becomes a chunk-level payload filter. The value
# lives once per document in Postgres, but Qdrant can only filter on what sits on the point being
# scored — so the same value must be written onto each chunk point. Pure set_payload (never a
# re-embed): idempotent, non-destructive merge, and a clean no-op for a document with no indexed
# chunks or no filterable metadata yet. The ingestion write-side hook and the collection-wide
# backfill both go through the SAME per-document sync.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, DocumentApi
from shared_libs.services.db.qdrant import QdrantClient, QdrantIndexApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


class FilterSyncFacade(LoggerClass):
    """Denormalise document-scope filterable metadata onto every chunk's Qdrant point payload."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (metadata values + chunk index flags).
            qdrant (QdrantClient): The vector store whose point payloads carry the filter.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def sync_document_filter_payloads(self, document_id: uuid.UUID) -> int:
        """
        Write a document's filterable document-scope metadata onto all its chunk points.

        The value is read once from Postgres and set (merged) onto every indexed chunk point, so a
        ``filters={field: value}`` search matches exactly the chunks of documents carrying it. Never
        re-embeds; re-running yields the same payload (idempotent). Skips cleanly when the document
        has no filterable metadata or no indexed chunk yet.

        Args:
            document_id (uuid.UUID): The document to synchronise.

        Returns:
            int: The number of chunk points patched (0 when there is nothing to carry or to filter).
        """
        # 1. Read the document, its filterable doc-scope metadata and its indexed chunk ids.
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                return 0
            values = await DocumentApi.get_filterable_metadata(session, document_id)
            chunk_ids = await ChunkApi.get_indexed_ids_for_document(session, document_id)

        # 2. Nothing to filter on, or no point to carry it → clean no-op.
        if not values or not chunk_ids:
            return 0

        # 3. Set the SAME payload keys on every chunk point (merge — other keys untouched).
        name = DatabaseHelpers.qdrant_collection_name(document.collection_id)
        payloads = {str(chunk_id): dict(values) for chunk_id in chunk_ids}
        await QdrantIndexApi.set_payload(self._qdrant.raw, name, payloads)
        self.logger.info(
            f"Synced {len(values)} filter field(s) onto {len(chunk_ids)} point(s) "
            f"for document {document_id}"
        )
        return len(chunk_ids)

    async def backfill_collection_filter_payloads(
        self, collection_id: uuid.UUID
    ) -> tuple[int, int]:
        """
        Run the per-document sync across every document of a collection (one-off backfill).

        The maintenance path for data ingested before document-scope filters were denormalised: no
        re-embed, just the same set_payload per document. Idempotent — safe to re-run.

        Args:
            collection_id (uuid.UUID): The collection whose documents are backfilled.

        Returns:
            tuple[int, int]: (documents that received a payload, total points patched).
        """
        # 1. Every document of the collection gets the same per-document sync.
        async with self._postgres.session() as session:
            documents = await DocumentApi.list_for_collection(session, collection_id)

        # 2. Accumulate what was actually patched (documents with metadata AND indexed chunks).
        documents_synced = 0
        points_patched = 0
        for document in documents:
            patched = await self.sync_document_filter_payloads(document.id)
            if patched:
                documents_synced += 1
                points_patched += patched

        self.logger.info(
            f"Backfilled filter payloads on collection {collection_id}: "
            f"{documents_synced} document(s), {points_patched} point(s)"
        )
        return documents_synced, points_patched


__all__ = ["FilterSyncFacade"]
