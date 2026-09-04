# ====== Code Summary ======
# IngestEnqueuer — the one place an ingestion job is handed to the queue. It enqueues, and if the
# queue put fails (a Redis blip), marks the freshly-committed job FAILED instead of leaving it PENDING
# forever. The reaper only collects RUNNING jobs, so an orphan PENDING would be invisible to every
# recovery path; failing it here keeps the job visibly terminal (and re-ingestable). Shared by all
# three enqueue sites — upload, single reingest and bulk reingest — so none can regress the pattern.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

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
            jobs (JobsFacade): The job lifecycle façade (marks the job FAILED on a queue error).
            document_id (str): The admitted document's UUID (string — the queue carries strings).
            job_id (str): The committed PENDING job driving the lifecycle.
            force (bool): When True, the run bypasses the stage cache (full recompute).

        Returns:
            bool: True when the job was enqueued; False when the queue put failed and the job was
                marked FAILED instead (the caller decides whether to surface an error or continue).
        """
        # 1. Try the queue put — the happy path leaves the job PENDING for the worker to claim.
        try:
            await queue.enqueue_ingest(document_id, job_id, force=force)
            return True
        # 2. The job is committed PENDING but never reached the queue (e.g. Redis down). The reaper
        #    only collects RUNNING jobs, so mark it FAILED here rather than leave an orphan PENDING.
        except Exception as exc:
            cls.logger.error(f"Enqueue failed for document {document_id} (job {job_id}): {exc}")
            # The queue seam carries strings; the job façade keys on a UUID.
            await jobs.mark_failed(uuid.UUID(job_id), f"Enqueue failed: {exc}", datetime.now(UTC))
            return False


__all__ = ["IngestEnqueuer"]
