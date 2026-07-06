# ====== Code Summary ======
# JobsFacade — the ingestion-observability surface: the job lifecycle transitions (each in its own
# small transaction, as the worker reports them) and the stage-event timeline the live UI reads.
# Pure Postgres; wraps JobApi so callers never manage sessions themselves.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.tables import Job, JobStageEvent


class JobsFacade(LoggerClass):
    """Job lifecycle + stage timeline, each call in its own transaction."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def get(self, job_id: uuid.UUID) -> Job | None:
        """Fetch a job by id."""
        async with self._postgres.session() as session:
            return await JobApi.get(session, job_id)

    async def list_for_collection(self, collection_id: uuid.UUID) -> list[Job]:
        """Return a collection's jobs, newest first."""
        async with self._postgres.session() as session:
            return await JobApi.list_for_collection(session, collection_id)

    async def mark_running(
        self, job_id: uuid.UUID, worker_id: str, attempt: int, started_at: datetime
    ) -> None:
        """Claim the job for a worker (retry-safe: clears the previous attempt's outcome)."""
        async with self._postgres.session() as session:
            await JobApi.mark_running(session, job_id, worker_id, attempt, started_at)

    async def set_progress(self, job_id: uuid.UUID, current_stage: str, progress: int) -> None:
        """Report the current stage and coarse progress."""
        async with self._postgres.session() as session:
            await JobApi.set_progress(session, job_id, current_stage, progress)

    async def mark_done(self, job_id: uuid.UUID, finished_at: datetime) -> None:
        """Complete the job successfully."""
        async with self._postgres.session() as session:
            await JobApi.mark_done(session, job_id, finished_at)

    async def mark_failed(self, job_id: uuid.UUID, error: str, finished_at: datetime) -> None:
        """Fail the job with its error message."""
        async with self._postgres.session() as session:
            await JobApi.mark_failed(session, job_id, error, finished_at)

    async def list_events(self, job_id: uuid.UUID) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order."""
        async with self._postgres.session() as session:
            return await JobApi.list_events(session, job_id)

    async def list_active(self) -> list[Job]:
        """Return every RUNNING job — the workers' live activity."""
        async with self._postgres.session() as session:
            return await JobApi.list_active(session)

    async def record_event(self, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline."""
        async with self._postgres.session() as session:
            return await JobApi.record_event(session, event)


__all__ = ["JobsFacade"]
