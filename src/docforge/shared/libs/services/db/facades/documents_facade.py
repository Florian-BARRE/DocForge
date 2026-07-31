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
from shared_libs.services.db.postgresql.apis import BlobApi, ChunkApi, DocumentApi, IRApi
from shared_libs.services.db.postgresql.tables import (
    Chunk,
    ChunkBlock,
    ChunkMetadata,
    Document,
    DocumentMetadata,
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

    async def list_for_collection(self, collection_id: uuid.UUID) -> list[Document]:
        """Return a collection's documents, newest first."""
        async with self._postgres.session() as session:
            return await DocumentApi.list_for_collection(session, collection_id)

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
            assembly order (the first entry is the chunk's primary block). A chunk with no blocks is
            absent from the map.
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
            await DocumentApi.delete(session, document_id)
            await session.flush()
            orphans = await BlobApi.find_unreferenced(session, candidates)
            await BlobApi.delete_rows(session, orphans)
        # 4. S3 last, AFTER the commit — a failed S3 delete only leaves harmless orphan objects.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        self.logger.info(f"Document {document_id} deleted ({len(orphans)} blobs purged)")
        return True


__all__ = ["DocumentsFacade"]
