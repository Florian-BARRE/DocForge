# ====== Code Summary ======
# Job worker models: the live per-worker activity view and the outcome of cancelling a job.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .status import JobStatus


class WorkerActivity(BaseModel):
    """
    One worker's live activity — its heartbeat-derived liveness plus any RUNNING jobs it owns.

    Attributes:
        worker_id (str): The worker's stable id (its hostname).
        worker_name (str | None): Its friendly display name (WORKER_NAME, defaults to the
            hostname); None only for a heartbeat row written before this column landed.
        alive (bool): Its heartbeat is fresher than the liveness threshold.
        busy (bool): It currently owns at least one RUNNING job.
        last_seen (datetime | None): Its last heartbeat tick (None when no heartbeat row exists).
        started_at (datetime | None): When the worker process registered (None when no heartbeat).
        max_jobs (int | None): Its configured parallel-job capacity (arq concurrency); None means
            unknown capacity (an old heartbeat row, or a worker on a build predating this field).
        cpu_percent (float | None): Its recent CPU utilisation percent, sampled at the last heartbeat
            (may exceed 100 on a multi-core host); None = not reported.
        mem_mb (float | None): Its resident memory in megabytes at the last heartbeat; None = not reported.
        mem_percent (float | None): Its resident memory as a percent of host RAM; None = not reported.
        jobs (list[JobStatus]): Its running jobs, live.
    """

    worker_id: str = Field(description="The worker's stable id (its hostname).")
    worker_name: str | None = Field(
        default=None,
        description="Friendly display name (WORKER_NAME, defaults to hostname); None for a "
        "pre-column row.",
    )
    alive: bool = Field(description="Heartbeat fresher than the liveness threshold.")
    busy: bool = Field(description="Owns at least one RUNNING job right now.")
    last_seen: datetime | None = Field(
        default=None, description="Last heartbeat tick (None when the worker has no heartbeat row)."
    )
    started_at: datetime | None = Field(
        default=None, description="When the worker process registered (None when no heartbeat)."
    )
    max_jobs: int | None = Field(
        default=None,
        description="The worker's configured parallel-job capacity (arq concurrency, = "
        "WORKER_CONCURRENCY). Null = unknown capacity: an old heartbeat row, or a worker on a build "
        "predating this field. The UI pairs it with the running-jobs count as a 'N running / max' chip.",
    )
    cpu_percent: float | None = Field(
        default=None,
        description="The worker process's recent CPU utilisation percent, sampled (via psutil) at the "
        "last heartbeat tick — may exceed 100 on a multi-core host. Null = not reported: an old "
        "heartbeat row, a build that does not sample resources, or the first (unprimed) tick / a "
        "psutil error.",
    )
    mem_mb: float | None = Field(
        default=None,
        description="The worker process's resident memory (RSS) in megabytes at the last heartbeat "
        "tick. Null = not reported (old row, non-sampling build, or a psutil error).",
    )
    mem_percent: float | None = Field(
        default=None,
        description="The worker process's resident memory as a percent of total host RAM at the last "
        "heartbeat tick. Null = not reported (old row, non-sampling build, or a psutil error).",
    )
    jobs: list[JobStatus] = Field(default_factory=list, description="Its running jobs, live.")


class WorkersLive(BaseModel):
    """
    Everything running right now, grouped by worker — the monitoring view.

    Attributes:
        workers (list[WorkerActivity]): One entry per active worker.
    """

    workers: list[WorkerActivity] = Field(
        default_factory=list, description="One entry per active worker."
    )


class CancelResult(BaseModel):
    """
    The typed outcome of a cancel request — what the job's state is after the call.

    Attributes:
        job_id (str): The targeted job's UUID.
        status (str): The job's status AFTER the call (cancelled / running).
        cancel_requested (bool): Whether a cooperative stop is now pending (true only while a
            running job is still winding down to the CANCELLED terminal state).
        outcome (str): cancelled (now terminal) | cancellation_requested (running, will stop at
            the next stage boundary).
        detail (str): A human-readable description of what happened.
    """

    job_id: str = Field(description="The targeted job's UUID.")
    status: str = Field(description="The job's status AFTER the call (cancelled / running).")
    cancel_requested: bool = Field(
        description="Whether a cooperative stop is now pending (true only while a running job is "
        "still winding down to the CANCELLED terminal state)."
    )
    outcome: str = Field(
        description="cancelled (now terminal) | cancellation_requested (running, will stop at "
        "the next stage boundary)."
    )
    detail: str = Field(description="A human-readable description of what happened.")
