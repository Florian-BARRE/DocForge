# ====== Code Summary ======
# BulkReingestService — the fan-out heart of a mass re-ingestion: given already-resolved target
# documents, it creates a FRESH ingestion job per document (document reset to PENDING) and enqueues
# each with the collection's wall-clock job timeout, returning one handle per job. It performs NO target
# resolution or validation (the router owns the fail-fast contract) and NO persistence beyond the
# per-document reingest admission — the worker does the actual full-pipeline run.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db import Database
from shared_libs.services.db.facades import ReingestOutcome
from shared_libs.services.db.postgresql.tables import Collection, Document

# ====== Local Project Imports ======
from ...utils.ingest_enqueuer import IngestEnqueuer
from ...utils.queue import QueueClient
from .models import ReingestJobHandle


@dataclass(slots=True)
class FanoutBatch:
    """The result of fanning out over a fetched document set: the handles + the skipped-in-flight count.

    Attributes:
        handles (list[ReingestJobHandle]): One handle per document a fresh job was minted + enqueued for.
        skipped_in_flight (int): Documents skipped because a run was ALREADY active for them (an older
            job still PENDING/RUNNING) — the per-document active-job invariant refuses a second run.
    """

    handles: list[ReingestJobHandle]
    skipped_in_flight: int


@dataclass(slots=True)
class CappedFanout:
    """The outcome of a capped fan-out: how many matched, how many were enqueued, and the handles.

    Attributes:
        matched (int): The full resolved target count (before the cap).
        enqueued (int): Jobs actually enqueued (<= the ceiling).
        capped (bool): True when ``matched`` exceeded the ceiling (the tail was NOT enqueued).
        ceiling (int): The per-call fan-out ceiling that was applied.
        skipped_in_flight (int): Kept documents skipped because a run was ALREADY active for them.
        handles (list[ReingestJobHandle]): One handle per enqueued run.
    """

    matched: int
    enqueued: int
    capped: bool
    ceiling: int
    skipped_in_flight: int
    handles: list[ReingestJobHandle]


class BulkReingestService(LoggerClass):
    """Fan out a full re-run across a collection's documents — one fresh job per document."""

    def __init__(self, database: Database, queue: QueueClient) -> None:
        """
        Args:
            database (Database): The persistence façade (per-document reingest admission).
            queue (QueueClient): The arq enqueue seam (carries ids only).
        """
        LoggerClass.__init__(self)
        self._database = database
        self._queue = queue

    async def enqueue_capped(
        self,
        collection: Collection,
        matched_ids: Sequence[uuid.UUID],
        ceiling: int,
        force: bool = False,
    ) -> CappedFanout:
        """
        Cap an already-resolved target set, fetch the kept documents, and fan out one job each.

        The single capped fan-out path BOTH reingest routes share (the collection-wide route and the
        corpus selector route), so neither can silently flood the queue: a match count above
        ``ceiling`` enqueues only the first N (deterministic order) and reports ``capped=true`` with
        the full ``matched`` count.

        Args:
            collection (Collection): The target collection (its job timeout caps arq's outer timeout).
            matched_ids (Sequence[uuid.UUID]): The resolved, already-authorised target ids.
            ceiling (int): The per-call fan-out ceiling.
            force (bool): When True, each run bypasses the stage cache (full recompute).

        Returns:
            CappedFanout: matched / enqueued / capped + the ceiling + one handle per enqueued run.
        """
        # 1. Cap the fan-out — never flood the queue with 100k jobs on one call.
        capped = len(matched_ids) > ceiling
        targets = list(matched_ids[:ceiling])
        if capped:
            self.logger.warning(
                f"Reingest on {collection.id}: {len(matched_ids)} matched, capped to {ceiling}"
            )

        # 2. Fetch the kept documents and fan out one full-pipeline job each.
        documents = await self._database.documents.get_by_ids(targets)
        batch = await self.enqueue(collection, documents, force=force)
        return CappedFanout(
            matched=len(matched_ids),
            enqueued=len(batch.handles),
            capped=capped,
            ceiling=ceiling,
            skipped_in_flight=batch.skipped_in_flight,
            handles=batch.handles,
        )

    async def enqueue(
        self,
        collection: Collection,
        documents: Sequence[Document],
        force: bool = False,
    ) -> FanoutBatch:
        """
        Create + enqueue one full re-ingestion job per target document.

        Idempotent per document: ``ingestion.reingest`` resets the document to PENDING and mints a
        fresh job, and the worker's run is a REPLACE (chunks/IR purged-then-inserted, Qdrant points
        deleted-by-document before upsert), so re-running the same corpus never accumulates.

        Args:
            collection (Collection): The target collection (its job timeout caps arq's outer timeout).
            documents (Sequence[Document]): The already-resolved, already-authorised targets.
            force (bool): When True, each run bypasses the stage cache (full recompute).

        Returns:
            FanoutBatch: One handle per enqueued run, plus how many documents were skipped because a
                run was ALREADY active for them (the per-document active-job invariant).
        """
        # 1. Per document: fresh job (doc → PENDING), then enqueue with the collection job timeout.
        handles: list[ReingestJobHandle] = []
        skipped_in_flight = 0
        for document in documents:
            result = await self._database.ingestion.reingest(document.id)
            if result.outcome is ReingestOutcome.NOT_FOUND:
                # The document vanished between resolution and admission (a concurrent delete) —
                # skip it rather than fail the whole batch; the caller sees it absent from handles.
                self.logger.warning(f"Skipped {document.id}: gone before re-ingest admission")
                continue
            if result.outcome is ReingestOutcome.ALREADY_ACTIVE:
                # A run is already queued/executing for this document — skip rather than mint a second
                # concurrent job (two parallel runs strand orphan Qdrant points). Counted separately so
                # the caller can report how many were skipped for being in flight.
                skipped_in_flight += 1
                self.logger.warning(
                    f"Skipped {document.id}: an ingestion job ({result.active_job_id}) is already "
                    f"active — not re-ingesting concurrently"
                )
                continue
            job = result.job
            # Shared enqueue-or-mark-failed: a Redis blip marks THIS job FAILED (never an orphan
            # PENDING) and we keep fanning out so one blip doesn't sink the whole batch.
            enqueued = await IngestEnqueuer.enqueue(
                self._queue, self._database.jobs, str(document.id), str(job.id), force=force
            )
            if not enqueued:
                continue
            handles.append(ReingestJobHandle(document_id=str(document.id), job_id=str(job.id)))

        # 2. One log line for the whole fan-out (the per-job lines live in the queue client).
        self.logger.info(
            f"Bulk re-ingest enqueued {len(handles)} job(s) for collection {collection.id} "
            f"({skipped_in_flight} skipped — already in flight)"
        )
        return FanoutBatch(handles=handles, skipped_in_flight=skipped_in_flight)


__all__ = ["BulkReingestService"]
