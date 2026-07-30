# ====== Code Summary ======
# IngestionFacade — the worker's persistence path, in pipeline order: dedup lookup, admission
# (document + job), blob storage (S3 then registry), the ONE-TRANSACTION save of everything a pure
# pipeline run produced (facts + pages + metadata + IR + chunks — idempotent on re-ingest via the
# purge-then-insert pattern), and the vector indexing (ensure the Qdrant collection from the schema,
# upsert the points, flag the chunks indexed).

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
                queries=payload.chunk_queries,
                entities=payload.entities,
            )
            # 4. The persisted truth is complete.
            await DocumentApi.set_status(session, document_id, DocumentStatus.DONE)
        self.logger.info(
            f"Ingestion saved for document {document_id}: "
            f"{len(payload.blocks)} blocks, {len(payload.chunks)} chunks"
        )

    async def mark_failed(self, document_id: uuid.UUID) -> None:
        """Flag the document's ingestion as failed (the job carries the error detail)."""
        async with self._postgres.session() as session:
            await DocumentApi.set_status(session, document_id, DocumentStatus.FAILED)

    async def index(
        self,
        collection_id: uuid.UUID,
        dense_dim: int,
        points: Sequence[QdrantPoint],
        colbert_dim: int | None = None,
    ) -> None:
        """
        Push the chunk vectors into Qdrant and flag the chunks indexed.

        The Qdrant collection is ensured (lazily created) from the CURRENT metadata schema; a
        dimension change without reindex surfaces as a loud upsert error, never silently.

        Args:
            collection_id (uuid.UUID): The target collection.
            dense_dim (int): Dense vector dimension (from the pipeline's embed config).
            points (Sequence[QdrantPoint]): The points (ids = chunk ids) with vectors + payload.
            colbert_dim (int | None): Per-token ColBERT dimension; when given (and only on a fresh
                collection), the ``content_colbert`` multi-vector is declared. None declares none.
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
            colbert_dim=colbert_dim,
        )
        # 2. Upsert, then flag the chunks as indexed.
        await QdrantIndexApi.upsert(self._qdrant.raw, name, points)
        async with self._postgres.session() as session:
            await ChunkApi.mark_indexed(session, [uuid.UUID(point.point_id) for point in points])
        self.logger.info(f"Indexed {len(points)} points into '{name}'")


__all__ = ["IngestionFacade"]
