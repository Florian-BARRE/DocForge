# ====== Code Summary ======
# BulkReingestService — the fan-out heart of a mass re-ingestion: given already-resolved target
# documents, it creates a FRESH ingestion job per document (document reset to PENDING) and enqueues
# each with the collection's wall-clock budget, returning one handle per job. It performs NO target
# resolution or validation (the router owns the fail-fast contract) and NO persistence beyond the
# per-document reingest admission — the worker does the actual full-pipeline run.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import Collection, Document

# ====== Local Project Imports ======
from ...utils.queue import QueueClient
from .models import ReingestJobHandle


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

    async def enqueue(
        self,
        collection: Collection,
        documents: Sequence[Document],
    ) -> list[ReingestJobHandle]:
        """
        Create + enqueue one full re-ingestion job per target document.

        Idempotent per document: ``ingestion.reingest`` resets the document to PENDING and mints a
        fresh job, and the worker's run is a REPLACE (chunks/IR purged-then-inserted, Qdrant points
        deleted-by-document before upsert), so re-running the same corpus never accumulates.

        Args:
            collection (Collection): The target collection (its job budget caps arq's outer timeout).
            documents (Sequence[Document]): The already-resolved, already-authorised targets.

        Returns:
            list[ReingestJobHandle]: One handle (document id + job id) per enqueued run.
        """
        # 1. Per document: fresh job (doc → PENDING), then enqueue with the collection budget.
        handles: list[ReingestJobHandle] = []
        for document in documents:
            result = await self._database.ingestion.reingest(document.id)
            if result is None:
                # The document vanished between resolution and admission (a concurrent delete) —
                # skip it rather than fail the whole batch; the caller sees it absent from handles.
                self.logger.warning(f"Skipped {document.id}: gone before re-ingest admission")
                continue
            _document, job = result
            try:
                await self._queue.enqueue_ingest(
                    str(document.id), str(job.id), collection.job_timeout_seconds
                )
            except Exception as exc:
                # The job is already committed PENDING but never made it onto the queue (e.g. a Redis
                # blip). The reaper only collects RUNNING jobs, so mark it FAILED here rather than
                # leaving an orphan PENDING — and keep fanning out so one blip doesn't sink the batch.
                self.logger.error(f"Enqueue failed for {document.id} (job {job.id}): {exc}")
                await self._database.jobs.mark_failed(
                    job.id, f"Enqueue failed: {exc}", datetime.now(UTC)
                )
                continue
            handles.append(ReingestJobHandle(document_id=str(document.id), job_id=str(job.id)))

        # 2. One log line for the whole fan-out (the per-job lines live in the queue client).
        self.logger.info(
            f"Bulk re-ingest enqueued {len(handles)} job(s) for collection {collection.id}"
        )
        return handles


__all__ = ["BulkReingestService"]
