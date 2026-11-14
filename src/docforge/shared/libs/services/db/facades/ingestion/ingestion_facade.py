# ====== Code Summary ======
# IngestionFacade — the worker's persistence path, in pipeline order: dedup lookup, admission
# (document + job), blob storage (S3 then registry), the ONE-TRANSACTION save of everything a pure
# pipeline run produced (facts + pages + metadata + IR + chunks — idempotent on re-ingest via the
# purge-then-insert pattern), and the vector indexing (ensure the Qdrant collection from the schema,
# upsert the fresh points, purge the document's leftover ones, flag the chunks indexed). Re-ingest is
# a REPLACE at every layer: Postgres purges-then-inserts, and Qdrant upserts the deterministic
# (document, ordinal) point ids in place, then drops the ids the new run no longer produced.
#
# A thin orchestrator behind ``Database.ingestion``: every public method delegates to
# IngestionAdmission (admit / reingest / dedup), IngestionPersister (blobs, save, status marks),
# TracePayloadStore (full trace payloads) or IngestionIndexer (Qdrant indexing); the public names and
# signatures are the contract callers rely on.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis.execution_tree import TraceRefs
from shared_libs.services.db.postgresql.tables import Blob, Document, DocumentMetadata, Job
from shared_libs.services.db.qdrant import QdrantClient, QdrantPoint
from shared_libs.services.db.s3 import S3Client, S3Object

# ====== Local Project Imports ======
from ..payloads import AdmissionResult, IngestionPayload, ReingestResult
from .ingestion_admission import IngestionAdmission
from .ingestion_indexer import IngestionIndexer
from .ingestion_persister import IngestionPersister
from .trace_payload_store import TracePayloadStore


class IngestionFacade(LoggerClass):
    """The worker's persistence path — admit, store blobs, save the run, index the vectors."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._admission = IngestionAdmission(postgres, s3)
        self._persister = IngestionPersister(postgres, s3)
        self._traces = TracePayloadStore(postgres, s3)
        self._indexer = IngestionIndexer(postgres, qdrant)

    # ---------------------- Admission (IngestionAdmission) ---------------------- #
    async def find_duplicate(
        self, collection_id: uuid.UUID, source_hash: str, pipeline_version: str
    ) -> Document | None:
        """Dedup lookup — the already-ingested document for this exact content+config, or None."""
        return await self._admission.find_duplicate(collection_id, source_hash, pipeline_version)

    async def admit(
        self,
        document: Document,
        job: Job,
        declared_metadata: Sequence[DocumentMetadata] = (),
    ) -> AdmissionResult:
        """
        Register the document (PENDING), its ingestion job and its DECLARED metadata — one tx.

        A lost concurrent-duplicate race resolves idempotently to the incumbent document (no job);
        any other integrity failure is re-raised. See ``IngestionAdmission.admit``.

        Args:
            document (Document): The document row to create (status PENDING).
            job (Job): The ingestion job row (document/collection ids filled here).
            declared_metadata (Sequence[DocumentMetadata]): User-declared field rows
                (document_id filled here).

        Returns:
            AdmissionResult: ``created=True`` + the fresh document/job when this call won the insert;
                ``created=False`` + the incumbent document (no job) on a lost duplicate race.
        """
        return await self._admission.admit(document, job, declared_metadata)

    async def reingest(
        self, document_id: uuid.UUID, replay_from: str | None = None
    ) -> ReingestResult:
        """
        Re-enqueue ingestion for an EXISTING document — no re-upload needed.

        Refuses a document that already has a live job (``ALREADY_ACTIVE``); ``replay_from`` stamps a
        post-IR stage on the job to re-run only that stage downstream. See
        ``IngestionAdmission.reingest``.

        Args:
            document_id (uuid.UUID): The document to re-ingest.
            replay_from (str | None): Replay from this stage instead of a full run (None = full run).

        Returns:
            ReingestResult: ADMITTED (+ document + fresh job) when a run was minted; NOT_FOUND for an
                unknown id; ALREADY_ACTIVE (+ the blocking job id) when a run is already in flight;
                NOT_REPLAYABLE when a replay was asked but no IR is persisted.
        """
        return await self._admission.reingest(document_id, replay_from)

    # ---------------------- Persistence (IngestionPersister) ---------------------- #
    async def store_blobs(self, objects: Sequence[S3Object], rows: Sequence[Blob]) -> None:
        """Store blob bytes in S3, then register them in Postgres (S3 first: orphans are harmless)."""
        await self._persister.store_blobs(objects, rows)

    async def save(
        self,
        document_id: uuid.UUID,
        payload: IngestionPayload,
        warning_reason: str | None = None,
    ) -> None:
        """
        Persist everything a pipeline run produced, in ONE transaction (idempotent on re-ingest).

        Superseded blobs are purged after the commit. See ``IngestionPersister.save``.

        Args:
            document_id (uuid.UUID): The admitted document.
            payload (IngestionPayload): The run's rows + learned facts.
            warning_reason (str | None): A non-fatal warning to stamp on the DONE document — set by
                the worker when a run completed cleanly but delivered zero chunks (nothing
                retrievable). None (the normal path) clears any stale warning on re-ingest.
        """
        await self._persister.save(document_id, payload, warning_reason)

    async def mark_processing(self, document_id: uuid.UUID) -> None:
        """Move the document PENDING → PROCESSING as the worker claims its job (guarded edge)."""
        await self._persister.mark_processing(document_id)

    async def mark_failed(self, document_id: uuid.UUID) -> None:
        """Flag the document's ingestion as failed (the job carries the error detail)."""
        await self._persister.mark_failed(document_id)

    async def mark_replay_failed(self, document_id: uuid.UUID, warning_reason: str) -> None:
        """
        Record a failed REPLAY without demoting the document (its previous content is still served).

        Args:
            document_id (uuid.UUID): The replayed document.
            warning_reason (str): The human-readable failure surfaced on the document.
        """
        await self._persister.mark_replay_failed(document_id, warning_reason)

    # ---------------------- Full trace tier (TracePayloadStore) ---------------------- #
    async def store_trace_payloads(
        self, job_id: uuid.UUID, record: NodeExecutionRecord, max_payload_bytes: int
    ) -> dict[str, TraceRefs]:
        """
        Store each node's FULL input/output payload in the object store (the full trace tier).

        Best-effort by contract: a store failure is logged and dropped, never failing an ingestion.
        See ``TracePayloadStore.store_trace_payloads``.

        Args:
            job_id (uuid.UUID): The job whose trace payloads are stored (its key prefix).
            record (NodeExecutionRecord): The run's outermost execution record.
            max_payload_bytes (int): Per-payload byte cap; a larger serialised payload is truncated.

        Returns:
            dict[str, TraceRefs]: Per node_path, the object-store keys of its stored input/output
                payloads (a side is absent when the node had no full payload or the store missed).
        """
        return await self._traces.store_trace_payloads(job_id, record, max_payload_bytes)

    # ---------------------- Vector indexing (IngestionIndexer) ---------------------- #
    async def index(
        self,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        dense_dim: int,
        points: Sequence[QdrantPoint],
        layout: VectorLayout | None = None,
    ) -> None:
        """
        Push a document's chunk vectors into Qdrant (replacing its old points) and flag them indexed.

        Upserts first, then purges the document's leftover points; see ``IngestionIndexer.index``.

        Args:
            collection_id (uuid.UUID): The target collection.
            document_id (uuid.UUID): The document whose points these are — its stale points are
                purged so a re-ingest never orphans the previous run's vectors.
            dense_dim (int): Dense vector dimension (from the pipeline's embed config).
            points (Sequence[QdrantPoint]): The points (ids = chunk ids) with vectors + payload.
            layout (VectorLayout | None): The embedder's config-derived layout (content axes + sparse
                IDF) — the store schema follows it; None = the legacy dense + sparse, no-IDF layout.
        """
        await self._indexer.index(collection_id, document_id, dense_dim, points, layout)


__all__ = ["IngestionFacade"]
