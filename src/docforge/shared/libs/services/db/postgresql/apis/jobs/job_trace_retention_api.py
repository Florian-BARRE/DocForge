# ====== Code Summary ======
# JobTraceRetentionApi — Trace-payload retention: the job-id sets whose object-store trace
# payloads a purge / GC reclaims, the reference clearing + footprint counter, and the age-based
# history prune.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import (
    Job,
    JobStageEvent,
    JobStatus,
)


class JobTraceRetentionApi:
    """Static data-access API: trace-payload retention id sets, ref clearing and the history prune."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobTraceRetentionApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def list_trace_job_ids_before(
        session: AsyncSession, cutoff: datetime, limit: int
    ) -> list[uuid.UUID]:
        """
        Return job ids older than ``cutoff`` that still carry stored full-trace payloads (bounded).

        The trace-retention GC purges the object-store payloads of aged jobs; the keys are job-prefixed
        (``trace/{job_id}/``), so a purge operates by job id. A job qualifies when it was created before
        the cutoff AND at least one of its stage-event rows still flags a stored full payload
        (``has_full_input``/``has_full_output``) — a job whose payloads were already purged (refs
        cleared) no longer matches, so the pass converges instead of re-purging forever. ``limit``
        bounds one GC batch.

        Args:
            session (AsyncSession): The active DB session.
            cutoff (datetime): Jobs created strictly before this are eligible.
            limit (int): Maximum job ids to return in one batch.

        Returns:
            list[uuid.UUID]: The eligible job ids (at most ``limit``), oldest first.
        """
        result = await session.execute(
            select(Job.id)
            .join(JobStageEvent, JobStageEvent.job_id == Job.id)
            .where(
                Job.created_at < cutoff,
                or_(
                    JobStageEvent.has_full_input.is_(True),
                    JobStageEvent.has_full_output.is_(True),
                ),
            )
            .group_by(Job.id, Job.created_at)
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_job_ids_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Return every job id of a document — the ids whose trace payloads a delete/reingest purges."""
        result = await session.execute(select(Job.id).where(Job.document_id == document_id))
        return list(result.scalars().all())

    @staticmethod
    async def list_job_ids_for_documents(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> list[uuid.UUID]:
        """Return every job id across a SET of documents — the bulk-delete trace-purge id set."""
        if not document_ids:
            return []
        result = await session.execute(
            select(Job.id).where(Job.document_id.in_(list(document_ids)))
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_job_ids_for_collection(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Return every job id of a collection — the ids whose trace payloads a collection delete purges."""
        result = await session.execute(select(Job.id).where(Job.collection_id == collection_id))
        return list(result.scalars().all())

    @staticmethod
    async def list_terminal_job_ids_for_collection(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """
        Return a collection's TERMINAL (done/failed/cancelled) job ids — the explicit trace-purge set.

        The trace-payload purge endpoint reclaims only jobs that are over: a PENDING/RUNNING job may be
        mid trace-finalize (``store_trace_payloads`` then ``persist_execution_tree``), so gathering it
        would race that write — the counter could be re-set to N after the bytes were prefix-deleted,
        or S3 objects could be stranded. Excluding the live rows (mirroring ``prune_history``'s
        terminal-only discipline) keeps the ``=0`` convergence sound; the in-flight job's trace becomes
        reclaimable by a later purge (or the retention GC) once it terminates. The document delete /
        reingest paths deliberately keep gathering ALL jobs and use ``list_job_ids_for_*`` instead.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection whose terminal job ids are gathered.

        Returns:
            list[uuid.UUID]: The collection's terminal job ids (empty when none are over).
        """
        result = await session.execute(
            select(Job.id).where(
                Job.collection_id == collection_id,
                Job.status.in_(JobStatus.terminal()),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_terminal_job_ids_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """
        Return a document's TERMINAL (done/failed/cancelled) job ids — the explicit trace-purge set.

        The document-scoped analogue of ``list_terminal_job_ids_for_collection``: the trace-payload
        purge reclaims only jobs that are over, so a PENDING/RUNNING job racing its trace-finalize is
        skipped and reclaimed once terminal. Delete/reingest keep using ``list_job_ids_for_document``.

        Args:
            session (AsyncSession): The active DB session.
            document_id (uuid.UUID): The document whose terminal job ids are gathered.

        Returns:
            list[uuid.UUID]: The document's terminal job ids (empty when none are over).
        """
        result = await session.execute(
            select(Job.id).where(
                Job.document_id == document_id,
                Job.status.in_(JobStatus.terminal()),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def clear_trace_refs(session: AsyncSession, job_ids: Sequence[uuid.UUID]) -> None:
        """
        Drop the full-trace object-store references on every stage-event row of the given jobs.

        Run right AFTER the GC deleted the jobs' ``trace/{job_id}/`` object-store space: the rows must
        no longer advertise a payload that is gone, so the refs are nulled and the ``has_full_*`` flags
        cleared. This both keeps the fetch route honest (it now reports the payload unavailable) and
        makes the retention pass converge (a cleared job no longer matches ``list_trace_job_ids_before``).

        Args:
            session (AsyncSession): The active DB session.
            job_ids (Sequence[uuid.UUID]): The jobs whose trace refs are cleared (empty → no-op).
        """
        if not job_ids:
            return
        ids = list(job_ids)
        await session.execute(
            update(JobStageEvent)
            .where(JobStageEvent.job_id.in_(ids))
            .values(
                input_ref=None,
                output_ref=None,
                has_full_input=False,
                has_full_output=False,
            )
        )
        # Zero the footprint counter in the SAME transaction: once the bytes are reclaimed the storage
        # footprint must converge (purge / retention GC / reingest-supersede all funnel through here).
        await session.execute(update(Job).where(Job.id.in_(ids)).values(trace_payload_bytes=0))

    @staticmethod
    async def set_trace_payload_bytes(
        session: AsyncSession, job_id: uuid.UUID, total_bytes: int
    ) -> None:
        """
        Record the total bytes of a job's stored FULL execution-trace payloads.

        Written best-effort right after ``store_trace_payloads`` persisted the payloads: it lets the
        storage footprint surface the ``trace/{job_id}/`` object-store space (which is NOT registry-
        tracked) via a plain SQL SUM, and the trace-payload purge zero it (through ``clear_trace_refs``)
        so the footprint converges once the bytes are reclaimed.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job whose trace-payload byte total is recorded.
            total_bytes (int): The summed size of the job's stored (content-addressed) trace objects.
        """
        await session.execute(
            update(Job).where(Job.id == job_id).values(trace_payload_bytes=total_bytes)
        )

    @staticmethod
    async def prune_history(session: AsyncSession, cutoff: datetime) -> int:
        """
        Delete TERMINAL jobs older than ``cutoff`` (with their stage-events) and return the count.

        The observability history (``job`` + ``job_stage_event``) is append-only and grows forever;
        this is the age-based retention sweep. Three safety invariants shape the predicate:

          1. Only TERMINAL jobs are eligible (``status IN (done, failed, cancelled)``) — a pending or
             running job is NEVER deleted, whatever its age.
          2. A job still carrying a stored FULL-trace payload (any stage-event flagging
             ``has_full_input``/``has_full_output``) is skipped. Those payloads live in the object
             store under a ``trace/{job_id}/`` prefix and are reclaimed by the SEPARATE trace GC,
             which keys off exactly these stage-event rows by job id; deleting the rows first would
             strand the S3 objects forever. The trace GC clears those flags once it reclaims a job's
             payloads, after which the row becomes prunable here — so the two sweeps converge instead
             of fighting. When trace retention is keep-forever (0), such a job's rows are deliberately
             retained to keep its payloads addressable.
          3. ``job_stage_event.job_id`` is ``ON DELETE CASCADE`` from ``job``, so deleting the job row
             removes its whole timeline at the DB level — no companion delete is needed.

        The leading ``ix_job_created_at`` index bounds the age scan.

        Args:
            session (AsyncSession): The active DB session.
            cutoff (datetime): Terminal jobs with ``created_at`` strictly before this are deleted.

        Returns:
            int: The number of job rows deleted.
        """
        # 1. Correlated existence probe: does this job still advertise a stored full-trace payload?
        has_full_trace = (
            select(JobStageEvent.id)
            .where(
                JobStageEvent.job_id == Job.id,
                or_(
                    JobStageEvent.has_full_input.is_(True),
                    JobStageEvent.has_full_output.is_(True),
                ),
            )
            .exists()
        )
        # 2. Age-based bulk delete of terminal, trace-free jobs (stage-events cascade with the row).
        result = await session.execute(
            delete(Job).where(
                Job.status.in_(tuple(JobStatus.terminal())),
                Job.created_at < cutoff,
                ~has_full_trace,
            )
        )
        return result.rowcount or 0


__all__ = ["JobTraceRetentionApi"]
