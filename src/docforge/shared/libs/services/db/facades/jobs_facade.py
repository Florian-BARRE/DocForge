# ====== Code Summary ======
# JobsFacade — the ingestion-observability surface: the job lifecycle transitions (each in its own
# small transaction, as the worker reports them) and the stage-event timeline the live UI reads.
# Pure Postgres; wraps JobApi so callers never manage sessions themselves.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime
from decimal import Decimal

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import DocumentApi, JobApi
from shared_libs.services.db.postgresql.tables import (
    DocumentStatus,
    Job,
    JobStageEvent,
    WorkerHeartbeat,
)


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

    async def last_successful_ingest_at(self, collection_id: uuid.UUID) -> datetime | None:
        """Return the finish time of the collection's most recent DONE ingest, or None."""
        async with self._postgres.session() as session:
            return await JobApi.last_successful_ingest_at(session, collection_id)

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

    async def set_items(
        self, job_id: uuid.UUID, items_done: int | None, items_total: int | None
    ) -> None:
        """Set the fan-out per-item counter (both None = reset when leaving a fan-out stage)."""
        async with self._postgres.session() as session:
            await JobApi.set_items(session, job_id, items_done, items_total)

    async def mark_done(self, job_id: uuid.UUID, finished_at: datetime) -> None:
        """Complete the job successfully."""
        async with self._postgres.session() as session:
            await JobApi.mark_done(session, job_id, finished_at)

    async def mark_failed(
        self,
        job_id: uuid.UUID,
        error: str,
        finished_at: datetime,
        failed_node_id: str | None = None,
        failed_node_kind: str | None = None,
        failed_item_index: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """Fail the job with its error message + structured breadcrumb; close its open stage row."""
        async with self._postgres.session() as session:
            await JobApi.mark_failed(
                session,
                job_id,
                error,
                finished_at,
                failed_node_id=failed_node_id,
                failed_node_kind=failed_node_kind,
                failed_item_index=failed_item_index,
                error_type=error_type,
            )

    async def list_events(self, job_id: uuid.UUID) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order."""
        async with self._postgres.session() as session:
            return await JobApi.list_events(session, job_id)

    async def list_active(self) -> list[Job]:
        """Return every RUNNING job — the workers' live activity."""
        async with self._postgres.session() as session:
            return await JobApi.list_active(session)

    async def list_heartbeats(self) -> list[WorkerHeartbeat]:
        """Return every worker heartbeat row — the fleet's liveness snapshot (idle-alive included)."""
        async with self._postgres.session() as session:
            return await JobApi.list_heartbeats(session)

    async def queue_depth(self, collection_id: uuid.UUID | None = None) -> tuple[int, int]:
        """Count (pending, running) jobs — fleet-wide when collection_id is None, else scoped."""
        async with self._postgres.session() as session:
            return await JobApi.queue_depth(session, collection_id)

    async def record_event(self, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline (returns it with its id assigned)."""
        async with self._postgres.session() as session:
            return await JobApi.record_event(session, event)

    async def finalize_event(
        self,
        event_id: uuid.UUID,
        status: str,
        finished_at: datetime,
        detail: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        cost_usd: Decimal | None,
    ) -> None:
        """Close an open stage-event row (opened at START) with its final outcome/usage."""
        async with self._postgres.session() as session:
            await JobApi.finalize_event(
                session,
                event_id,
                status,
                finished_at,
                detail,
                prompt_tokens,
                completion_tokens,
                cost_usd,
            )

    async def upsert_heartbeat(
        self, worker_id: str, last_seen: datetime, started_at: datetime
    ) -> None:
        """Register/refresh a worker's liveness heartbeat row (idle-but-alive visibility)."""
        async with self._postgres.session() as session:
            await JobApi.upsert_heartbeat(session, worker_id, last_seen, started_at)

    async def delete_heartbeat(self, worker_id: str) -> None:
        """De-register a worker on clean shutdown — its heartbeat row vanishes immediately."""
        async with self._postgres.session() as session:
            await JobApi.delete_heartbeat(session, worker_id)

    async def prune_stale_heartbeats(self, older_than_seconds: float) -> list[str]:
        """Delete heartbeat rows frozen past the cutoff (crashed workers); return the removed ids."""
        async with self._postgres.session() as session:
            return await JobApi.prune_stale_heartbeats(session, older_than_seconds)

    async def add_usage(
        self,
        job_id: uuid.UUID,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
    ) -> None:
        """Fold a stage's token/cost usage into the job's per-document running totals (null-safe)."""
        async with self._postgres.session() as session:
            await JobApi.add_usage(session, job_id, prompt_tokens, completion_tokens, cost_usd)

    async def avg_stage_durations(self, collection_id: uuid.UUID) -> dict[str, float]:
        """Average per-stage duration (seconds) over the collection's DONE jobs — the ETA basis."""
        async with self._postgres.session() as session:
            return await JobApi.avg_stage_durations(session, collection_id)

    async def collection_cost(self, collection_id: uuid.UUID) -> tuple[int, int, float, int]:
        """Roll up the collection's per-document meters: (prompt, completion, usd, doc count)."""
        async with self._postgres.session() as session:
            return await JobApi.collection_cost(session, collection_id)

    async def reap_stale(self, older_than_seconds: float) -> list[uuid.UUID]:
        """
        Fail every RUNNING job whose progress froze past the threshold — orphaned-job recovery.

        A dev worker hot-reload (or a crash) drops the in-flight arq task, but the DB job row stays
        RUNNING forever and its document PROCESSING. This lists such wedged jobs and, for each, marks
        the job FAILED with an operator-clear reason AND flags its owning document FAILED (so the
        document is visibly re-ingestable). Idempotent under concurrency: a row already reaped no
        longer matches ``status == RUNNING``, so a second pass — or a second worker — is a harmless
        no-op that simply finds nothing to reap.

        Args:
            older_than_seconds (float): A RUNNING job idle longer than this is reaped.

        Returns:
            list[uuid.UUID]: The reaped job ids (empty when nothing was stale).
        """
        minutes = int(older_than_seconds // 60)
        error = (
            f"reaped: job made no progress for >{minutes}m — presumed orphaned by a worker restart"
        )
        reaped: list[uuid.UUID] = []
        async with self._postgres.session() as session:
            for job in await JobApi.list_stale(session, older_than_seconds):
                now = datetime.now(UTC)
                await JobApi.mark_failed(session, job.id, error=error, finished_at=now)
                if job.document_id is not None:
                    await DocumentApi.set_status(session, job.document_id, DocumentStatus.FAILED)
                reaped.append(job.id)
        if reaped:
            self.logger.warning(f"Reaped {len(reaped)} stale job(s): {error}")
        return reaped


__all__ = ["JobsFacade"]
