# ====== Code Summary ======
# IngestionFacade — the worker's persistence path, in pipeline order: dedup lookup, admission
# (document + job), blob storage (S3 then registry), the ONE-TRANSACTION save of everything a pure
# pipeline run produced (facts + pages + metadata + IR + chunks — idempotent on re-ingest via the
# purge-then-insert pattern), and the vector indexing (ensure the Qdrant collection from the schema,
# delete the document's stale points, upsert the fresh ones, flag the chunks indexed). Re-ingest is
# a REPLACE at every layer: Postgres purges-then-inserts, and Qdrant deletes-by-document before
# upsert (the run remints chunk ids, so a plain upsert would orphan the previous run's points).

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    BlobApi,
    ChunkApi,
    CollectionApi,
    DocumentApi,
    IRApi,
    JobApi,
)
from shared_libs.services.db.postgresql.tables import (
    Blob,
    Document,
    DocumentMetadata,
    DocumentStatus,
    Job,
)
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
)
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .payloads import IngestionPayload


class IngestionFacade(LoggerClass):
    """The worker's persistence path — admit, store blobs, save the run, index the vectors."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3

    async def find_duplicate(
        self, collection_id: uuid.UUID, source_hash: str, pipeline_version: str
    ) -> Document | None:
        """Dedup lookup — the already-ingested document for this exact content+config, or None."""
        async with self._postgres.session() as session:
            return await DocumentApi.find(session, collection_id, source_hash, pipeline_version)

    async def admit(
        self,
        document: Document,
        job: Job,
        declared_metadata: Sequence[DocumentMetadata] = (),
    ) -> tuple[Document, Job]:
        """
        Register the document (PENDING), its ingestion job and its DECLARED metadata — one tx.

        The declared (user-origin) metadata is part of the admission: the worker reads it back
        to rebuild the pipeline's run input, so a half-admitted document must never exist.

        Args:
            document (Document): The document row to create (status PENDING).
            job (Job): The ingestion job row (document/collection ids filled here).
            declared_metadata (Sequence[DocumentMetadata]): User-declared field rows
                (document_id filled here).

        Returns:
            tuple[Document, Job]: The created rows, ids assigned.
        """
        async with self._postgres.session() as session:
            created = await DocumentApi.create(session, document)
            job.document_id = created.id
            job.collection_id = created.collection_id
            created_job = await JobApi.create(session, job)
            if declared_metadata:
                for row in declared_metadata:
                    row.document_id = created.id
                await DocumentApi.replace_metadata(session, created.id, list(declared_metadata))
        return created, created_job

    async def reingest(self, document_id: uuid.UUID) -> tuple[Document, Job] | None:
        """
        Re-enqueue ingestion for an EXISTING document — no re-upload needed.

        The original bytes are content-addressed (``source_hash``) and the worker refetches them,
        the collection's CURRENT pipeline is read at run time, and a run is idempotent (the previous
        chunks/IR/pages are purged in ``save`` and the previous Qdrant points are deleted-by-document
        in ``index`` before the fresh points are upserted — a REPLACE, never an accumulation). So
        re-processing a document — e.g. after a pipeline or engine change — is just a fresh job on
        the same document, reset to PENDING. The USER-declared metadata rows survive (never touched
        here).

        Args:
            document_id (uuid.UUID): The document to re-ingest.

        Returns:
            tuple[Document, Job] | None: The document + the freshly-created job, or None when the
                document does not exist.
        """
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                return None
            job = Job(document_id=document.id, collection_id=document.collection_id)
            created_job = await JobApi.create(session, job)
            await DocumentApi.set_status(session, document_id, DocumentStatus.PENDING)
        return document, created_job

    async def store_blobs(self, objects: Sequence[S3Object], rows: Sequence[Blob]) -> None:
        """
        Store blob bytes in S3, then register them in Postgres.

        S3 first: if the registry write then fails, the orphan S3 objects are harmless; the
        reverse order would register rows whose bytes do not exist.
        """
        # 1. The bytes.
        if objects:
            async with self._s3.client() as s3:
                await S3ObjectApi.put_many(s3, self._s3.bucket, objects)
        # 2. The registry rows — one bulk insert (idempotent per content hash).
        async with self._postgres.session() as session:
            await BlobApi.register_many(session, rows)

    async def save(self, document_id: uuid.UUID, payload: IngestionPayload) -> None:
        """
        Persist everything a pipeline run produced, in ONE transaction.

        Idempotent on re-ingest: the document's previous chunks and IR are purged first, then the
        fresh rows inserted, so re-running the same document never conflicts on primary keys.

        Args:
            document_id (uuid.UUID): The admitted document.
            payload (IngestionPayload): The run's rows + learned facts.
        """
        async with self._postgres.session() as session:
            # 1. The facts the pipeline learned about the document.
            await DocumentApi.update_facts(
                session,
                document_id,
                title=payload.title,
                language=payload.language,
                page_count=payload.page_count,
                source_kind=payload.source_kind,
                pdf_blob_hash=payload.pdf_blob_hash,
                simhash=payload.simhash,
            )
            # 2. Pages + document-scope metadata (replace semantics).
            await DocumentApi.replace_pages(session, document_id, payload.pages)
            await DocumentApi.replace_metadata(session, document_id, payload.document_metadata)
            # 3. Purge the previous run's chunks and IR (re-ingest idempotency), then insert fresh.
            await ChunkApi.delete_for_document(session, document_id)
            await IRApi.delete_for_document(session, document_id)
            await IRApi.persist_ir(
                session,
                payload.blocks,
                block_tables=payload.block_tables,
                block_figures=payload.block_figures,
                enrichments=payload.enrichments,
                attempts=payload.attempts,
            )
            await ChunkApi.persist_chunks(
                session,
                payload.chunks,
                payload.composition,
                metadata=payload.chunk_metadata,
                entities=payload.entities,
            )
            # 4. The persisted truth is complete.
            await DocumentApi.set_status(session, document_id, DocumentStatus.DONE)
        self.logger.info(
            f"Ingestion saved for document {document_id}: "
            f"{len(payload.blocks)} blocks, {len(payload.chunks)} chunks"
        )

    async def mark_processing(self, document_id: uuid.UUID) -> None:
        """
        Move the document PENDING → PROCESSING as the worker claims its job.

        Guarded to the PENDING → PROCESSING edge (see ``DocumentApi.mark_processing``): the terminal
        DONE/FAILED writes at the end of the run always win, so a failure mid-run never leaves the
        document stuck in PROCESSING.
        """
        async with self._postgres.session() as session:
            await DocumentApi.mark_processing(session, document_id)

    async def mark_failed(self, document_id: uuid.UUID) -> None:
        """Flag the document's ingestion as failed (the job carries the error detail)."""
        async with self._postgres.session() as session:
            await DocumentApi.set_status(session, document_id, DocumentStatus.FAILED)

    async def index(
        self,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        dense_dim: int,
        points: Sequence[QdrantPoint],
    ) -> None:
        """
        Push a document's chunk vectors into Qdrant (replacing its old points) and flag them indexed.

        The Qdrant collection is ensured (lazily created) from the CURRENT metadata schema; a
        dimension change without reindex surfaces as a loud upsert error, never silently. Because
        each run mints FRESH chunk point ids (the translator's chunk-UUID remap), a re-ingest's new
        points would NOT overwrite the previous run's — so the document's old points are deleted
        first (scoped to this one document_id), making a re-ingest a REPLACE, not an accumulation.
        On a first ingest the delete is a harmless no-op (the document has no points yet).

        Args:
            collection_id (uuid.UUID): The target collection.
            document_id (uuid.UUID): The document whose points these are — its stale points are
                purged first so a re-ingest never orphans the previous run's vectors.
            dense_dim (int): Dense vector dimension (from the pipeline's embed config).
            points (Sequence[QdrantPoint]): The points (ids = chunk ids) with vectors + payload.
        """
        # 1. Derive the vector space from the schema (and re-check the slug guard defensively).
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
        # 2. Purge this document's previous points BEFORE upserting the fresh ones — the run remints
        #    chunk ids, so without this a re-ingest would leave the old points orphaned (live
        #    document_id + enabled payload → polluting the candidate pool and growing Qdrant
        #    unbounded). Scoped to the single document; a first ingest deletes nothing.
        await QdrantIndexApi.delete_by_document(self._qdrant.raw, name, document_id)
        # 3. Upsert, then flag the chunks as indexed.
        await QdrantIndexApi.upsert(self._qdrant.raw, name, points)
        async with self._postgres.session() as session:
            await ChunkApi.mark_indexed(session, [uuid.UUID(point.point_id) for point in points])
        self.logger.info(f"Indexed {len(points)} points into '{name}'")


__all__ = ["IngestionFacade"]
