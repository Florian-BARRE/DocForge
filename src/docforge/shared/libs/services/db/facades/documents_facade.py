# ====== Code Summary ======
# DocumentsFacade — reading, inspecting and deleting documents. Inspection exposes everything for
# debugging: the raw IR vs the enriched IR (IRBundle), the stored (enriched) chunks with their
# composition (to recompute the raw form) and their generated metadata. Deletion runs the coherent
# cross-store order: Qdrant points first, PG cascade, then the reference-filtered blob purge, S3 last.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    ArtifactCacheApi,
    BlobApi,
    ChunkApi,
    DocumentApi,
    DocumentQueryApi,
    DocumentQuerySpec,
    IRApi,
)
from shared_libs.services.db.postgresql.tables import (
    Chunk,
    ChunkBlock,
    ChunkMetadata,
    Document,
    DocumentMetadata,
    DocumentStatus,
    Page,
)
from shared_libs.services.db.qdrant import QdrantClient, QdrantIndexApi
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .payloads import IRBundle


class DocumentsFacade(LoggerClass):
    """Document reading, inspection (raw vs enriched, chunks, traces) and coherent deletion."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3

    # -------------------- catalogue --------------------
    async def get(self, document_id: uuid.UUID) -> Document | None:
        """Fetch a document by id."""
        async with self._postgres.session() as session:
            return await DocumentApi.get(session, document_id)

    async def get_by_ids(self, document_ids: Sequence[uuid.UUID]) -> list[Document]:
        """Bulk-fetch documents by id (the search-hydration source-identity read)."""
        async with self._postgres.session() as session:
            return await DocumentApi.get_by_ids(session, document_ids)

    async def get_filterable_metadata_for_documents(
        self, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, dict]:
        """Bulk filterable document-scope metadata for a set of documents (search hydration)."""
        async with self._postgres.session() as session:
            return await DocumentApi.get_filterable_metadata_for_documents(session, document_ids)

    async def list_for_collection(
        self,
        collection_id: uuid.UUID,
        status: DocumentStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Document]:
        """Return a collection's documents, newest first — optionally status-filtered and paged."""
        async with self._postgres.session() as session:
            return await DocumentApi.list_for_collection(
                session, collection_id, status, limit, offset
            )

    async def count_for_collection(
        self, collection_id: uuid.UUID, status: DocumentStatus | None = None
    ) -> int:
        """Count a collection's documents (optionally status-filtered) — the estimate scope size."""
        async with self._postgres.session() as session:
            return await DocumentApi.count_for_collection(session, collection_id, status)

    async def count_by_collections(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Document count of each collection in ONE grouped query — the fleet-dashboard doc-count."""
        async with self._postgres.session() as session:
            return await DocumentApi.count_by_collections(session, collection_ids)

    async def count_chunks_by_collections(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Chunk count of each collection in ONE grouped query — the fleet-dashboard chunk-count."""
        async with self._postgres.session() as session:
            return await ChunkApi.count_by_collections(session, collection_ids)

    # -------------------- grid query --------------------
    async def query(
        self, collection_id: uuid.UUID, spec: DocumentQuerySpec, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        """
        Return one filtered/sorted/paginated page of a collection's documents + the total match count.

        The page rows and the count run under the SAME predicates in one session, so the total the
        grid pager shows can never disagree with the rows it renders. Metadata bulk-load is a
        SEPARATE call (``get_metadata_for_documents``) keyed on the returned page ids — no N+1.

        Args:
            collection_id (uuid.UUID): The owning collection (always the first predicate).
            spec (DocumentQuerySpec): The fully-resolved filter + sort.
            limit (int): Page size (the caller clamps it to the configured ceiling).
            offset (int): Page offset (deep offsets are acceptable for v1; see the contract note).

        Returns:
            tuple[list[Document], int]: the page of rows, and the total number of matches.
        """
        async with self._postgres.session() as session:
            rows = await DocumentQueryApi.query(session, collection_id, spec, limit, offset)
            total = await DocumentQueryApi.count(session, collection_id, spec)
        return rows, total

    async def resolve_query_ids(
        self, collection_id: uuid.UUID, spec: DocumentQuerySpec, limit: int | None = None
    ) -> list[uuid.UUID]:
        """Return document ids matching a filter — the target set of a filter-selector (``limit``-bounded)."""
        async with self._postgres.session() as session:
            return await DocumentQueryApi.resolve_ids(session, collection_id, spec, limit)

    async def get_metadata_for_documents(
        self, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[DocumentMetadata]]:
        """Bulk-load every metadata value for a page of documents, grouped by document (no N+1)."""
        async with self._postgres.session() as session:
            return await DocumentApi.get_metadata_for_documents(session, document_ids)

    async def get_metadata(self, document_id: uuid.UUID) -> list[DocumentMetadata]:
        """Return the document's metadata values."""
        async with self._postgres.session() as session:
            return await DocumentApi.get_metadata(session, document_id)

    async def get_pages(self, document_id: uuid.UUID) -> list[Page]:
        """Return the document's pages, in order."""
        async with self._postgres.session() as session:
            return await DocumentApi.get_pages(session, document_id)

    # -------------------- inspection --------------------
    async def get_ir(self, document_id: uuid.UUID) -> IRBundle:
        """The full IR for inspection — raw blocks + details, and every enrichment."""
        async with self._postgres.session() as session:
            return IRBundle(
                blocks=await IRApi.get_blocks(session, document_id),
                tables=await IRApi.get_tables(session, document_id),
                figures=await IRApi.get_figures(session, document_id),
                enrichments=await IRApi.get_document_enrichments(session, document_id),
            )

    async def get_chunks(self, document_id: uuid.UUID) -> list[Chunk]:
        """The document's chunks (stored = the enriched, embedded form), in order."""
        async with self._postgres.session() as session:
            return await ChunkApi.get_for_document(session, document_id)

    async def get_chunks_by_ids(self, chunk_ids: list[uuid.UUID]) -> list[Chunk]:
        """Fetch chunks by id — the search-graph hydration path (bulk read, read-only)."""
        async with self._postgres.session() as session:
            return await ChunkApi.get_by_ids(session, chunk_ids)

    async def get_block_locations_for_chunks(
        self, chunk_ids: list[uuid.UUID]
    ) -> dict[str, list[dict]]:
        """
        Bulk block locations (page + bbox) per chunk — the search-hit location read.

        Lets a search hit self-cite WHERE on the page it came from (so a UI can draw a box), in ONE
        query for the whole hit page. The bbox is the block's stored, normalised [x0, y0, x1, y1] in
        [0, 1] — the frontend multiplies by the page image dimensions.

        Args:
            chunk_ids (list[uuid.UUID]): The hydrated hit chunks to locate.

        Returns:
            dict[str, list[dict]]: chunk_id (str) → its blocks' ``{block_id, page, bbox}`` in
            assembly order (the first entry is the chunk's primary block). ``page`` is None for a
            page-less document (no page render). A chunk with no blocks is absent from the map.
        """
        if not chunk_ids:
            return {}
        async with self._postgres.session() as session:
            rows = await ChunkApi.get_block_locations_for_chunks(session, chunk_ids)
        grouped: dict[str, list[dict]] = {}
        for chunk_id, block_id, page, bbox in rows:
            grouped.setdefault(str(chunk_id), []).append(
                {"block_id": block_id, "page": page, "bbox": bbox}
            )
        return grouped

    async def collections_for_chunks(self, chunk_ids: list[uuid.UUID]) -> list[str]:
        """Distinct collections owning a set of chunks — the scope gate for chunk mutations."""
        async with self._postgres.session() as session:
            ids = await ChunkApi.collections_for_chunks(session, chunk_ids)
        return [str(collection_id) for collection_id in ids]

    async def get_document_chunk_composition(self, document_id: uuid.UUID) -> list[ChunkBlock]:
        """Every chunk's composition for a document, ordered by chunk then position (bulk)."""
        async with self._postgres.session() as session:
            return await ChunkApi.get_composition_for_document(session, document_id)

    async def get_document_chunk_metadata(self, document_id: uuid.UUID) -> list[ChunkMetadata]:
        """Every chunk's generated metadata for a document — one query, grouped by the caller."""
        async with self._postgres.session() as session:
            return await ChunkApi.get_metadata_for_document(session, document_id)

    # -------------------- blobs --------------------
    async def collections_for_blob(self, content_hash: str) -> list[str]:
        """Collections whose documents reference this blob — the scope gate for the byte route."""
        async with self._postgres.session() as session:
            ids = await BlobApi.collections_for_hash(session, content_hash)
        return [str(collection_id) for collection_id in ids]

    async def read_blob(self, content_hash: str) -> tuple[bytes, str] | None:
        """Read a blob's bytes + mime type by content hash (original, PDF, render, crop)."""
        async with self._postgres.session() as session:
            row = await BlobApi.get(session, content_hash)
        if row is None:
            return None
        async with self._s3.client() as s3:
            data = await S3ObjectApi.get(s3, self._s3.bucket, row.s3_key)
        return data, row.mime_type

    # -------------------- deletion --------------------
    async def delete(self, document_id: uuid.UUID) -> bool:
        """
        Delete a document everywhere — Qdrant points first, PG cascade, filtered blob purge.

        Returns:
            bool: Whether the document existed.
        """
        async with self._postgres.session() as session:
            # 1. Locate it (its collection names the Qdrant collection).
            document = await DocumentApi.get(session, document_id)
            if document is None:
                return False
            name = DatabaseHelpers.qdrant_collection_name(document.collection_id)
            # 2. Derived index first — no orphan points that search could still return.
            await QdrantIndexApi.delete_by_document(self._qdrant.raw, name, document_id)
            # 3. Gather purge candidates, cascade-delete, keep only true orphans.
            candidates = await BlobApi.collect_hashes_for_document(session, document_id)
            # Drop the document's stage-cache pointer rows too (its cached parse is now unreachable);
            # the orphaned S3 bytes are reclaimed by the cache GC's global orphan sweep.
            await ArtifactCacheApi.delete_for_documents(session, [document_id])
            await DocumentApi.delete(session, document_id)
            await session.flush()
            # Guarded purge: the reference test is re-evaluated INSIDE the DELETE (not at an earlier
            # SELECT), so a hash a concurrent ingest re-referenced between the flush and the commit is
            # kept — and only the rows actually removed come back for the S3 delete.
            orphans = await BlobApi.delete_unreferenced(session, candidates)
        # 4. S3 last, AFTER the commit — a failed S3 delete only leaves harmless orphan objects.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        self.logger.info(f"Document {document_id} deleted ({len(orphans)} blobs purged)")
        return True

    async def delete_many(self, document_ids: Sequence[uuid.UUID]) -> int:
        """
        Delete a SET of documents everywhere, in bounded batches, in the single-delete's coherent order.

        Generalises ``delete`` for the 100k-scale bulk path WITHOUT a long single transaction: the
        target set is processed in bounded chunks (``_DELETE_BATCH_SIZE``), each chunk one short
        transaction that is fully set-based (no per-document round-trip) — Qdrant points first (one
        ``MatchAny`` per collection so the vectors are gone before any search could return them), then
        the Postgres cascade (``DELETE ... WHERE id IN``), then the reference-filtered blob purge (a
        blob still referenced by a surviving document — even one in a later batch — is kept), and S3
        last, after each chunk's commit, so a failed object delete only leaves harmless orphans. The
        whole matched set is always processed (no silent cap — unlike the reingest fan-out).

        Args:
            document_ids (Sequence[uuid.UUID]): The already-resolved, already-authorised targets.

        Returns:
            int: How many documents actually existed and were deleted.
        """
        # 1. De-duplicate while preserving order; nothing to do on an empty set.
        unique_ids = list(dict.fromkeys(document_ids))
        if not unique_ids:
            return 0

        # 2. Delete in bounded batches so transaction/lock/memory footprint stays flat at any scale.
        total_deleted = 0
        for start in range(0, len(unique_ids), _DELETE_BATCH_SIZE):
            batch = unique_ids[start : start + _DELETE_BATCH_SIZE]
            total_deleted += await self._delete_batch(batch)
        self.logger.info(
            f"Bulk-deleted {total_deleted} document(s) across {len(unique_ids)} target(s)"
        )
        return total_deleted

    async def _delete_batch(self, batch: Sequence[uuid.UUID]) -> int:
        """Delete one bounded batch coherently (Qdrant points → PG cascade → orphan-only S3 purge)."""
        async with self._postgres.session() as session:
            # 1. Resolve the LIVE targets in this batch and group them by their Qdrant collection.
            documents = await DocumentApi.get_by_ids(session, batch)
            if not documents:
                return 0
            live_ids = [document.id for document in documents]
            by_collection: dict[uuid.UUID, list[uuid.UUID]] = {}
            for document in documents:
                by_collection.setdefault(document.collection_id, []).append(document.id)

            # 2. Derived index first — purge every collection's points before the PG cascade.
            for collection_id, ids in by_collection.items():
                name = DatabaseHelpers.qdrant_collection_name(collection_id)
                await QdrantIndexApi.delete_by_documents(self._qdrant.raw, name, ids)

            # 3. Candidates (batched), set-based cascade delete, then keep only true orphans.
            candidates = await BlobApi.collect_hashes_for_documents(session, live_ids)
            # Drop the batch's stage-cache pointer rows; the cache GC sweeps the orphaned S3 bytes.
            await ArtifactCacheApi.delete_for_documents(session, live_ids)
            deleted = await DocumentApi.delete_many(session, live_ids)
            await session.flush()
            # Guarded purge (see ``delete``): the reference re-check lives in the DELETE, so a
            # concurrently-ingested hash is never stranded; RETURNING gives the exact S3 delete set.
            orphans = await BlobApi.delete_unreferenced(session, candidates)

        # 4. S3 last, AFTER the commit — a failed object delete only leaves harmless orphans.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        return deleted


# The bulk-delete chunk size: each batch is one short transaction, so a 100k delete stays a stream
# of bounded units rather than a single long-held write lock. Tune with load, not correctness.
_DELETE_BATCH_SIZE = 500


__all__ = ["DocumentsFacade"]
