# ====== Code Summary ======
# Response models for the jobs resource, mirrored field-for-field from the DocForge backend router
# models: the live ingestion status, one node of the execution trace, the full trace, and the live
# per-worker activity view.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


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
        description="A RUNNING job idle past the stall threshold — an early wedge warning."
    )
    total_prompt_tokens: int = Field(
        description="Prompt tokens billed across this job's paid text-gen calls."
    )
    total_completion_tokens: int = Field(
        description="Completion tokens billed across this job's paid text-gen calls."
    )
    cost_usd: float = Field(
        description="USD cost of this job's paid calls (0 when nothing priceable)."
    )


class JobEvent(BaseModel):
    """
    One node of the job's execution trace — written by the worker at each stage end.

    Attributes:
        stage (str): The pipeline node id.
        status (str): success / failed / skipped.
        started_at (datetime | None): Node start.
        finished_at (datetime | None): Node end.
        detail (str | None): Duration, or the error when failed.
    """

    stage: str = Field(description="The pipeline node id.")
    status: str = Field(description="success / failed / skipped.")
    started_at: datetime | None = Field(default=None, description="Node start.")
    finished_at: datetime | None = Field(default=None, description="Node end.")
    detail: str | None = Field(default=None, description="Duration, or the error when failed.")
    prompt_tokens: int | None = Field(
        default=None, description="Prompt tokens billed by this stage; null when it made none."
    )
    completion_tokens: int | None = Field(
        default=None, description="Completion tokens billed by this stage; null when none."
    )
    cost_usd: float | None = Field(
        default=None, description="USD cost of this stage; null when no usage or unknown price."
    )


class JobTrace(BaseModel):
    """
    A job's full per-node trace, in execution order.

    Attributes:
        job_id (str): The traced job.
        events (list[JobEvent]): One entry per stage run.
    """

    job_id: str = Field(description="The traced job.")
    events: list[JobEvent] = Field(default_factory=list, description="One entry per stage run.")


class WorkerActivity(BaseModel):
    """
    One worker's live activity — derived from its RUNNING jobs (no extra heartbeat).

    Attributes:
        worker_id (str): The worker's hostname.
        jobs (list[JobStatus]): Its running jobs, live.
    """

    worker_id: str = Field(description="The worker's hostname.")
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


__all__ = ["JobStatus", "JobEvent", "JobTrace", "WorkerActivity", "WorkersLive"]
