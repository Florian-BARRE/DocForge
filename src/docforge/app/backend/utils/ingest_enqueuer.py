# ====== Code Summary ======
# IngestEnqueuer — the one place an ingestion job is handed to the queue. It enqueues, and if the
# queue put fails (a Redis blip), fails the freshly-committed PENDING job (and its document) instead of
# leaving it PENDING forever. The reaper only collects RUNNING jobs, so an orphan PENDING would be
# invisible to every recovery path AND would hold the per-document active-job lock (its predicate covers
# PENDING), wedging reingest at ALREADY_ACTIVE; failing it here through the terminate path keeps the job
# visibly terminal, frees the lock and leaves the document re-ingestable. Shared by all three enqueue
# sites — upload, single reingest and bulk reingest — so none can regress the pattern.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import JobsFacade

# ====== Local Project Imports ======
from .queue import QueueClient


class IngestEnqueuer:
    """Static gateway: enqueue an ingestion job, marking it FAILED if the queue put fails."""

    logger = loggerplusplus.bind(identifier="IngestEnqueuer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IngestEnqueuer is a static-only class and cannot be instantiated.")

    @classmethod
    async def enqueue(
        cls,
        queue: QueueClient,
        jobs: JobsFacade,
        document_id: str,
        job_id: str,
        *,
        force: bool = False,
    ) -> bool:
        """
        Enqueue one ingestion; on a queue failure, mark the job FAILED (never an orphan PENDING).

        Args:
            queue (QueueClient): The arq enqueue seam (carries ids only).
            jobs (JobsFacade): The job lifecycle façade (fails the job + document on a queue error).
            document_id (str): The admitted document's UUID (string — the queue carries strings).
            job_id (str): The committed PENDING job driving the lifecycle.
            force (bool): When True, the run bypasses the stage cache (full recompute).

        Returns:
            bool: True when the job was enqueued; False when the queue put failed and the job was
                failed instead (the caller decides whether to surface an error or continue).
        """
        # 1. Try the queue put — the happy path leaves the job PENDING for the worker to claim.
        try:
            await queue.enqueue_ingest(document_id, job_id, force=force)
            return True
        # 2. The job is committed PENDING but never reached the queue (e.g. Redis down). ``mark_failed``
        #    is RUNNING-only (it would silently no-op on a PENDING row), leaving an orphan PENDING that
        #    holds the per-document active lock and the reaper never collects; ``abandon_ingest`` routes
        #    through the terminate path (admits PENDING) to flip the job FAILED, free the lock and mirror
        #    the document FAILED (re-ingestable), best-effort.
        except Exception as exc:
            cls.logger.error(f"Enqueue failed for document {document_id} (job {job_id}): {exc}")
            # The queue seam carries strings; the job façade keys on a UUID.
            await jobs.abandon_ingest(uuid.UUID(job_id), f"Enqueue failed: {exc}")
            return False


__all__ = ["IngestEnqueuer"]
