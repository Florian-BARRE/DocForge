# ====== Code Summary ======
# CollectionTransferFacade — the single store gateway the collection export/import ENGINE talks to,
# so the engine (a worker lib) touches no client directly. EXPORT reads are streamed a document at a
# time (``read_document_export`` bundles one document's whole row set in one short session) plus a
# batched Qdrant ``scroll`` and one-blob-at-a-time byte reads. IMPORT writes just persist whatever
# rows the importer hands over (``restore_rows`` inserts a whole table in one transaction) — the id
# REMAP that keeps a bundle collision-free on any target lives in the importer, not here. Blob
# storage, vector indexing and the rollback delete reuse the ingestion/collections façades so the
# cross-store coherence rules are not duplicated here.

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    BlobApi,
    ChunkApi,
    CollectionApi,
    DocumentApi,
    IRApi,
    TransferApi,
)
from shared_libs.services.db.postgresql.tables import (
    Blob,
    Collection,
    ConfigVersion,
    MetadataField,
)
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
    VectorNames,
)
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# ====== Local Project Imports ======
from .collections_facade import CollectionsFacade
from .helpers import DatabaseHelpers
from .ingestion_facade import IngestionFacade
from .transfer_payloads import DocumentExportRows


class CollectionTransferFacade(LoggerClass):
    """The store gateway for collection export (streamed reads) and import (id-remapping writes)."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3
        # Reuse the coherent cross-store paths (create/delete, blob store, vector index).
        self._collections = CollectionsFacade(postgres, qdrant, s3)
        self._ingestion = IngestionFacade(postgres, qdrant, s3)

    # ==================== EXPORT (reads) ====================
    async def get_collection(self, collection_id: uuid.UUID) -> Collection | None:
        """Fetch the source collection row."""
        async with self._postgres.session() as session:
            return await CollectionApi.get(session, collection_id)

    async def get_schema(self, collection_id: uuid.UUID) -> list[MetadataField]:
        """Fetch the collection's metadata schema."""
        async with self._postgres.session() as session:
            return await CollectionApi.get_schema(session, collection_id)

    async def list_config_versions(self, collection_id: uuid.UUID) -> list[ConfigVersion]:
        """Fetch the collection's config snapshot history (newest first)."""
        async with self._postgres.session() as session:
            return await CollectionApi.list_config_versions(session, collection_id)

    async def list_document_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        """List every document id of the collection (lightweight — ids only, streamed per-doc after)."""
        async with self._postgres.session() as session:
            documents = await DocumentApi.list_for_collection(session, collection_id)
        return [document.id for document in documents]

    async def read_document_export(self, document_id: uuid.UUID) -> DocumentExportRows:
        """Read one document's ENTIRE row set for the bundle, in a single session."""
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                raise ValueError(f"document {document_id} vanished during export")
            return DocumentExportRows(
                document=document,
                metadata=await DocumentApi.get_metadata_with_names(session, document_id),
                pages=await DocumentApi.get_pages(session, document_id),
                blocks=await IRApi.get_blocks(session, document_id),
                tables=await IRApi.get_tables(session, document_id),
                figures=await IRApi.get_figures(session, document_id),
                enrichments=await IRApi.get_document_enrichments(session, document_id),
                chunks=await ChunkApi.get_for_document(session, document_id),
                composition=await ChunkApi.get_composition_for_document(session, document_id),
                chunk_metadata=await ChunkApi.get_metadata_with_names_for_document(
                    session, document_id
                ),
            )

    async def collect_blob_hashes(self, collection_id: uuid.UUID) -> list[str]:
        """Every unique blob hash the collection's documents reference."""
        async with self._postgres.session() as session:
            return await BlobApi.collect_hashes_for_collection(session, collection_id)

    async def get_blob_rows(self, hashes: Sequence[str]) -> list[Blob]:
        """The registry rows (hash, key, mime, size, kind) for a set of blob hashes."""
        async with self._postgres.session() as session:
            return await BlobApi.get_many(session, hashes)

    async def read_blob_bytes(self, s3_key: str) -> bytes:
        """Read one blob's raw bytes from S3 by its object key (streamed by the caller, one at a time)."""
        async with self._s3.client() as client:
            return await S3ObjectApi.get(client, self._s3.bucket, s3_key)

    # ==================== DELIVERY (bundle bytes over HTTP) ====================
    async def stream_bundle(
        self, s3_key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        """
        Stream an export bundle's bytes from S3 in bounded chunks (never whole in memory).

        Backs the authenticated download endpoint's ``StreamingResponse``: the shared S3 client is
        kept open for the whole iteration (exiting the ``client()`` scope does not close it), so the
        generator can pull windows straight from S3 to the HTTP response.

        Args:
            s3_key (str): The bundle object's key (the tracking row's ``s3_key``).
            chunk_size (int): The per-read window in bytes.

        Yields:
            bytes: The next window of the bundle's bytes.
        """
        async with self._s3.client() as client:
            async for chunk in S3ObjectApi.stream(client, self._s3.bucket, s3_key, chunk_size):
                yield chunk

    async def stage_bundle(self, s3_key: str, path: Any, content_type: str) -> int:
        """
        Publish an uploaded import bundle from a spooled local file to S3 (no in-memory buffering).

        Backs the import endpoint: the router spools the multipart upload to a temp file, then this
        streams that file to S3 under a staging key with a known Content-Length (``put_file``). The
        worker later downloads it from that key.

        Args:
            s3_key (str): The staging object key to publish under.
            path (Any): The local spooled-file path to upload.
            content_type (str): The object's content type.

        Returns:
            int: The uploaded object's size in bytes.
        """
        async with self._s3.client() as client:
            return await S3ObjectApi.put_file(client, self._s3.bucket, s3_key, path, content_type)

    async def gc_expired_bundles(self, now: datetime) -> list[uuid.UUID]:
        """
        Delete every expired export bundle everywhere — the S3 object AND its tracking row.

        Nothing GC's these otherwise: the download route refuses an expired bundle, but the S3 object
        and the ``collection_transfer`` row leak forever without this sweep (an unbounded storage +
        row leak). Per row: drop the S3 object first (best-effort — a missing object is fine, the S3
        delete is idempotent), then delete the row, so a crash mid-sweep never orphans a row pointing
        at a still-present object. Backs the worker's ``gc_expired_transfers`` cron.

        Args:
            now (datetime): The cutoff — any export whose ``expires_at`` is before this is reclaimed.

        Returns:
            list[uuid.UUID]: The ids of the transfers actually reclaimed (empty when none expired).
        """
        # 1. Find the expired export bundles that still hold an S3 object (one short read).
        async with self._postgres.session() as session:
            rows = await TransferApi.list_expired(session, now)

        # 2. Per row: reclaim the bytes, then the tracking row (bytes-first, so no row ever outlives
        #    its object pointing at a still-present blob). One row's failure (e.g. a transient S3
        #    error) must not head-of-line-block the rest of the sweep — log it and move on; the row
        #    stays expired and is retried next cycle.
        deleted: list[uuid.UUID] = []
        for row in rows:
            try:
                async with self._s3.client() as client:
                    await S3ObjectApi.delete(client, self._s3.bucket, row.s3_key)
                async with self._postgres.session() as session:
                    await TransferApi.delete(session, row.id)
                deleted.append(row.id)
            except Exception:
                self.logger.exception(f"GC failed to reclaim expired transfer {row.id}; will retry")
        if deleted:
            self.logger.info(f"GC reclaimed {len(deleted)} expired export bundle(s)")
        return deleted

    async def dense_dim(self, collection_id: uuid.UUID) -> int:
        """
        The Qdrant ``content_dense`` vector size (0 when the collection has no vector space yet).

        Captured in the manifest and replayed on import: the size is fixed at the target's first
        ``ensure`` and cannot change without a reindex, so the bundle must carry it.
        """
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if not await self._qdrant.raw.collection_exists(name):
            return 0
        params = (await self._qdrant.raw.get_collection(name)).config.params
        vectors = params.vectors
        if isinstance(vectors, dict) and VectorNames.CONTENT_DENSE in vectors:
            return int(vectors[VectorNames.CONTENT_DENSE].size)
        return 0

    async def scroll_points(
        self, collection_id: uuid.UUID, batch_size: int = 256
    ) -> AsyncIterator[Any]:
        """
        Stream every Qdrant point (id + named vectors + payload) in bounded batches.

        Yields the raw qdrant-client records; the exporter serializes them. A collection never
        embedded (no Qdrant space) yields nothing rather than raising.
        """
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if not await self._qdrant.raw.collection_exists(name):
            return
        offset: Any = None
        while True:
            points, offset = await self._qdrant.raw.scroll(
                collection_name=name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for point in points:
                yield point
            if offset is None:
                break

    # ==================== IMPORT (writes) ====================
    async def name_taken(self, name: str) -> bool:
        """Whether a collection already claims this (unique) name on the target server."""
        return await self._collections.get_by_name(name) is not None

    async def create_collection(
        self, collection: Collection, fields: list[MetadataField]
    ) -> Collection:
        """Create the NEW collection + its schema (fresh id + fresh autoincrement field ids)."""
        return await self._collections.create(collection, fields)

    async def field_id_map(self, collection_id: uuid.UUID) -> dict[str, int]:
        """field_name → the freshly-minted field id, for the metadata int-id remap."""
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        return {row.field_name: row.id for row in schema}

    async def restore_rows(self, rows: Sequence[object]) -> None:
        """
        Insert one table's rows (ids already remapped by the importer) in ONE transaction.

        The importer calls this per table in FK order, so every referenced id is already committed
        by the time a dependent table is inserted. Blocks and chunks carry a DEFERRED self-FK
        (parent_id), checked at COMMIT — inserting a whole table in a single transaction is what
        makes those parent references resolve regardless of row order.
        """
        rows = list(rows)
        if not rows:
            return
        async with self._postgres.session() as session:
            session.add_all(rows)

    async def store_blobs(self, objects: Sequence[S3Object], rows: Sequence[Blob]) -> None:
        """Store blob bytes (S3) then register them (idempotent) — reuses the ingestion path."""
        await self._ingestion.store_blobs(objects, rows)

    async def ensure_vector_space(self, collection_id: uuid.UUID, dense_dim: int) -> None:
        """Create the Qdrant collection from the schema + the manifest dense_dim (idempotent)."""
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        DatabaseHelpers.validate_vector_slugs(schema)
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        await QdrantCollectionApi.ensure(
            self._qdrant.raw,
            name,
            dense_dim=dense_dim,
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
        )

    async def upsert_points(self, collection_id: uuid.UUID, points: Sequence[QdrantPoint]) -> None:
        """Upsert points VERBATIM by id (= chunk id) into the (already ensured) vector space."""
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        await QdrantIndexApi.upsert(self._qdrant.raw, name, points)

    async def rollback_collection(self, collection_id: uuid.UUID) -> None:
        """Delete a half-imported collection everywhere (Qdrant drop → PG cascade → orphan blobs)."""
        await self._collections.delete(collection_id)


__all__ = ["CollectionTransferFacade"]
