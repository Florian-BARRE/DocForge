# ====== Code Summary ======
# IngestionPersister — the write half of the ingestion persistence path: blob storage (S3 then the
# Postgres registry), the ONE-TRANSACTION save of everything a pure pipeline run produced (idempotent
# on re-ingest via purge-then-insert, superseded blobs reclaimed), and the document status marks
# (processing / failed / replay-failed). Internal collaborator of IngestionFacade; callers go through
# ``Database.ingestion``.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import BlobApi, ChunkApi, DocumentApi, IRApi
from shared_libs.services.db.postgresql.tables import Blob, DocumentStatus
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# ====== Local Project Imports ======
from ..payloads import IngestionPayload


class IngestionPersister(LoggerClass):
    """Persist blobs, the run's rows (one tx) and the document's status transitions."""

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

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

    async def save(
        self,
        document_id: uuid.UUID,
        payload: IngestionPayload,
        warning_reason: str | None = None,
    ) -> None:
        """
        Persist everything a pipeline run produced, in ONE transaction.

        Idempotent on re-ingest: the document's previous chunks and IR are purged first, then the
        fresh rows inserted, so re-running the same document never conflicts on primary keys.

        Re-ingest also PURGES superseded blobs. Postgres and Qdrant are REPLACED here, but blobs are
        content-addressed and only ever added (``store_blobs`` ran before this) — so a re-ingest whose
        renders/crops/canonical-PDF differ byte-wise (a config or engine change) would leak the old
        objects in S3 + the registry forever. So the set of blobs the document referenced BEFORE the
        purge is snapshotted, and after the fresh rows land any of those now-unreferenced (re-checked
        at delete time, so a hash still shared by another document is kept) is removed — mirroring the
        document DELETE path. The original source bytes survive (still referenced by ``source_hash``).

        Args:
            document_id (uuid.UUID): The admitted document.
            payload (IngestionPayload): The run's rows + learned facts.
            warning_reason (str | None): A non-fatal warning to stamp on the DONE document — set by
                the worker when a run completed cleanly but delivered zero chunks (nothing
                retrievable). None (the normal path) clears any stale warning on re-ingest.
        """
        async with self._postgres.session() as session:
            # 0. Snapshot the blobs the document references NOW — the supersede candidates, gathered
            #    BEFORE the purge so the OLD renders/crops/canonical-PDF are captured.
            superseded_candidates = await BlobApi.collect_hashes_for_document(session, document_id)
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
            )
            await ChunkApi.persist_chunks(
                session,
                payload.chunks,
                payload.composition,
                metadata=payload.chunk_metadata,
            )
            # 4. The persisted truth is complete — unless a force-cancel raced in (guarded DONE). The
            #    chunk count is denormalized here (0 for the empty case) and the optional warning is
            #    stamped so a 0-chunk run reads as DONE-with-warning, not FAILED.
            await DocumentApi.finalize_done(
                session,
                document_id,
                warning_reason=warning_reason,
                chunk_count=len(payload.chunks),
            )
            # 5. Purge the blobs this run superseded: flush so the FRESH pages/figures/PDF hashes are
            #    visible to the reference re-check, then delete only the old hashes nothing references
            #    anymore (a byte-identical render re-used across runs, or the source, is kept).
            await session.flush()
            orphans = await BlobApi.delete_unreferenced(session, superseded_candidates)
        # 6. S3 last, AFTER the commit — a failed object delete only leaves harmless orphan bytes.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        self.logger.info(
            f"Ingestion saved for document {document_id}: "
            f"{len(payload.blocks)} blocks, {len(payload.chunks)} chunks "
            f"({len(orphans)} superseded blob(s) purged)"
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

    async def mark_replay_failed(self, document_id: uuid.UUID, warning_reason: str) -> None:
        """
        Record a failed REPLAY without demoting the document (its previous content is still served).

        A replay persists nothing before its single downstream commit, so a failure leaves the prior
        chunks/points intact: the document keeps its DONE/FAILED status and gets a visible warning.
        Only a document with no trustworthy prior status (PENDING/PROCESSING — admission reset it)
        falls back to FAILED.

        Args:
            document_id (uuid.UUID): The replayed document.
            warning_reason (str): The human-readable failure surfaced on the document.
        """
        async with self._postgres.session() as session:
            await DocumentApi.flag_replay_failure(session, document_id, warning_reason)


__all__ = ["IngestionPersister"]
