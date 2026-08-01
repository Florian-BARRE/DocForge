# ====== Code Summary ======
# Pydantic models for the jobs router — the live ingestion status the UI polls.

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import JobStatus as JobStatusEnum

# A RUNNING job idle longer than this shows as ``stalled`` — an EARLY warning the UI can surface
# before the worker reaper hard-fails it (WORKER_REAP_STALE_SECONDS, 20m). Deliberately half the
# reap window: the operator sees the wedge coming, then the reaper resolves it.
STALLED_AFTER_SECONDS = 600


class JobStatus(BaseModel):
    """
    One ingestion job's live state — written by the worker, only read here.

    Attributes:
        job_id (str): The job row's UUID.
        document_id (str): The document being ingested.
        collection_id (str): Its collection.
        status (str): queued / running / done / failed.
        progress (int): 0–100 (completed pipeline nodes over total).
        current_stage (str | None): The node currently (or last) executed.
        error (str | None): The failure, verbatim — only set when status is failed.
        attempt (int): arq retry attempt (1 = first run).
        started_at (datetime | None): When the worker picked it up.
        finished_at (datetime | None): When it ended (done or failed).
        updated_at (datetime): Last progress/lifecycle write — freezes when a job wedges.
        stalled (bool): A RUNNING job idle past STALLED_AFTER_SECONDS (an early wedge warning).
    """

    job_id: str = Field(description="The job row's UUID.")
    document_id: str = Field(description="The document being ingested.")
    collection_id: str = Field(description="Its collection.")
    status: str = Field(description="queued / running / done / failed.")
    progress: int = Field(description="0-100, completed pipeline nodes over total.")
    current_stage: str | None = Field(default=None, description="Node currently/last executed.")
    error: str | None = Field(default=None, description="Failure detail when status=failed.")
    attempt: int = Field(description="arq retry attempt (1 = first run).")
    started_at: datetime | None = Field(default=None, description="Picked up by the worker at.")
    finished_at: datetime | None = Field(default=None, description="Ended (done or failed) at.")
    updated_at: datetime = Field(description="Last progress/lifecycle write (freezes on a wedge).")
    stalled: bool = Field(
        description="A RUNNING job idle past the stall threshold — an early wedge warning surfaced "
        "before the worker reaper hard-fails it."
    )

    @classmethod
    def from_row(cls, job: Any) -> "JobStatus":
        """Map one job row to its polling model (shared by the poll routes and the SSE stream)."""
        # Only a RUNNING job can stall: its updated_at bumps on every progress write, so a value
        # older than the threshold means progress has frozen. done/failed/pending are never stalled.
        stalled = (
            job.status == JobStatusEnum.RUNNING
            and job.updated_at is not None
            and (datetime.now(UTC) - job.updated_at).total_seconds() > STALLED_AFTER_SECONDS
        )
        return cls(
            job_id=str(job.id),
            document_id=str(job.document_id),
            collection_id=str(job.collection_id),
            status=job.status.value,
            progress=job.progress,
            current_stage=job.current_stage,
            error=job.error,
            attempt=job.attempt,
            started_at=job.started_at,
            finished_at=job.finished_at,
            updated_at=job.updated_at,
            stalled=stalled,
        )


class JobEvent(BaseModel):
    """One node of the job's execution trace — written by the worker at each stage end."""

    stage: str = Field(description="The pipeline node id.")
    status: str = Field(description="success / failed / skipped.")
    started_at: datetime | None = Field(default=None, description="Node start.")
    finished_at: datetime | None = Field(default=None, description="Node end.")
    detail: str | None = Field(default=None, description="Duration, or the error when failed.")

    @classmethod
    def from_row(cls, event: Any) -> "JobEvent":
        """Map one stage-event row to its trace model (shared by the trace route and the stream)."""
        return cls(
            stage=event.stage,
            status=event.status,
            started_at=event.started_at,
            finished_at=event.finished_at,
            detail=event.detail,
        )


class JobTrace(BaseModel):
    """A job's full per-node trace, in execution order."""

    job_id: str = Field(description="The traced job.")
    events: list[JobEvent] = Field(default_factory=list, description="One entry per stage run.")


class WorkerActivity(BaseModel):
    """One worker's live activity — derived from its RUNNING jobs (no extra heartbeat)."""

    worker_id: str = Field(description="The worker's hostname.")
    jobs: list[JobStatus] = Field(default_factory=list, description="Its running jobs, live.")


class WorkersLive(BaseModel):
    """Everything running right now, grouped by worker — the monitoring view."""

    workers: list[WorkerActivity] = Field(default_factory=list)


__all__ = ["JobStatus", "JobEvent", "JobTrace", "WorkerActivity", "WorkersLive"]
