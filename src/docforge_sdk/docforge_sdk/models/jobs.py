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
        document_filename (str | None): The document's filename, joined at read (None if the
            document is gone).
        collection_id (str): Its collection.
        collection_name (str | None): The collection's name, joined at read (None if the
            collection is gone).
        status (str): queued / running / done / failed / cancelled.
        cancel_requested (bool): A cooperative stop has been requested; the running job stops at
            its next stage boundary (still 'running' until it does).
        progress (int): 0–100 (completed pipeline nodes over total).
        current_stage (str | None): The node currently (or last) executed.
        error (str | None): The failure, verbatim — only set when status is failed.
        attempt (int): arq retry attempt (1 = first run).
        started_at (datetime | None): When the worker picked it up.
        finished_at (datetime | None): When it ended (done or failed).
        items_done (int | None): Child items finished in the current fan-out stage (None off it).
        items_total (int | None): The current fan-out stage's width (None when not in a fan-out).
        failed_node_id (str | None): The deepest node that raised — only set on a failed job.
        failed_node_kind (str | None): That node's kind/family label — only set on a failed job.
        failed_item_index (int | None): The fan-out item index the failure sits in (None outside one).
        error_type (str | None): The exception class name of the failure (e.g. "TimeoutError").
    """

    job_id: str = Field(description="The job row's UUID.")
    document_id: str = Field(description="The document being ingested.")
    document_filename: str | None = Field(
        default=None,
        description="The document's filename, joined at read (None if the document is gone).",
    )
    collection_id: str = Field(description="Its collection.")
    collection_name: str | None = Field(
        default=None,
        description="The collection's name, joined at read (None if the collection is gone).",
    )
    status: str = Field(description="queued / running / done / failed / cancelled.")
    cancel_requested: bool = Field(
        default=False,
        description="A cooperative stop has been requested; the running job stops at its next "
        "stage boundary (still 'running' until it does).",
    )
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
    items_done: int | None = Field(
        default=None, description="Child items finished in the current fan-out stage (None off it)."
    )
    items_total: int | None = Field(
        default=None, description="The current fan-out stage's width (None when not in a fan-out)."
    )
    failed_node_id: str | None = Field(
        default=None, description="Deepest node that raised — only set on a failed job."
    )
    failed_node_kind: str | None = Field(
        default=None, description="That node's kind/family label — only set on a failed job."
    )
    failed_item_index: int | None = Field(
        default=None, description="Fan-out item index the failure sits in (None outside a fan-out)."
    )
    error_type: str | None = Field(
        default=None, description="Exception class name of the failure (e.g. 'TimeoutError')."
    )


class JobEvent(BaseModel):
    """
    One node of the job's execution trace — written by the worker at each stage end.

    Attributes:
        stage (str): The pipeline node id.
        status (str): success / failed / skipped.
        node_kind (str | None): The stage's structural kind (action/group/foreach) or the node's
            concrete kind — None for rows written before this column landed.
        started_at (datetime | None): Node start.
        finished_at (datetime | None): Node end.
        detail (str | None): Duration, or the error when failed.
    """

    stage: str = Field(description="The pipeline node id.")
    status: str = Field(description="success / failed / skipped.")
    node_kind: str | None = Field(
        default=None,
        description="The stage's structural kind (action/group/foreach) or the node's concrete "
        "kind — None for rows written before this column landed.",
    )
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
    One worker's live activity — its heartbeat-derived liveness plus any RUNNING jobs it owns.

    Attributes:
        worker_id (str): The worker's stable id (its hostname).
        worker_name (str | None): Its friendly display name (WORKER_NAME, defaults to the
            hostname); None only for a heartbeat row written before this column landed.
        alive (bool): Its heartbeat is fresher than the liveness threshold.
        busy (bool): It currently owns at least one RUNNING job.
        last_seen (datetime | None): Its last heartbeat tick (None when no heartbeat row exists).
        started_at (datetime | None): When the worker process registered (None when no heartbeat).
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


__all__ = [
    "JobStatus",
    "JobEvent",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "CancelResult",
]
