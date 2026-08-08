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
        total_prompt_tokens (int): The document's lifetime input tokens across paid text-gen calls.
        total_completion_tokens (int): The document's lifetime output tokens.
        cost_usd (float): The document's lifetime USD cost (0 while no priceable call has run).
        items_done (int | None): Child items finished in the CURRENT fan-out stage (None off fan-out).
        items_total (int | None): The current fan-out's width (None when not in a fan-out stage).
        failed_node_id (str | None): The deepest node that raised (only set on a failed job).
        failed_node_kind (str | None): That node's kind/family label (only set on a failed job).
        failed_item_index (int | None): The fan-out item index the failure sits in (None outside one).
        error_type (str | None): The exception class name (e.g. "TimeoutError") — set on failure.
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
    total_prompt_tokens: int = Field(
        description="Document's lifetime input tokens across paid text-gen (LLM/VLM/structgen) calls."
    )
    total_completion_tokens: int = Field(
        description="Document's lifetime output tokens across paid text-gen calls."
    )
    cost_usd: float = Field(
        description="Document's lifetime USD cost of paid calls (0 until a priceable call runs)."
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
            total_prompt_tokens=job.total_prompt_tokens,
            total_completion_tokens=job.total_completion_tokens,
            cost_usd=float(job.cost_usd),
            items_done=job.items_done,
            items_total=job.items_total,
            failed_node_id=job.failed_node_id,
            failed_node_kind=job.failed_node_kind,
            failed_item_index=job.failed_item_index,
            error_type=job.error_type,
        )


class JobEvent(BaseModel):
    """One node of the job's execution trace — written by the worker at each stage end."""

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
        default=None,
        description="Paid input tokens for this stage (None when it made no paid call).",
    )
    completion_tokens: int | None = Field(
        default=None, description="Paid output tokens for this stage (None when no paid call)."
    )
    cost_usd: float | None = Field(
        default=None,
        description="USD cost of this stage (None when it made no paid call OR its model is "
        "unpriced — the tokens are still reported).",
    )

    @classmethod
    def from_row(cls, event: Any) -> "JobEvent":
        """Map one stage-event row to its trace model (shared by the trace route and the stream)."""
        return cls(
            stage=event.stage,
            status=event.status,
            node_kind=event.node_kind,
            started_at=event.started_at,
            finished_at=event.finished_at,
            detail=event.detail,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            cost_usd=None if event.cost_usd is None else float(event.cost_usd),
        )


class JobTrace(BaseModel):
    """A job's full per-node trace, in execution order."""

    job_id: str = Field(description="The traced job.")
    events: list[JobEvent] = Field(default_factory=list, description="One entry per stage run.")


class WorkerActivity(BaseModel):
    """
    One worker's live activity — its heartbeat-derived liveness plus any RUNNING jobs it owns.

    ``alive`` and ``busy`` are two INDEPENDENT signals: a worker with a fresh heartbeat but no
    running job is ``alive=True, busy=False`` (idle-but-alive, previously invisible), while a worker
    whose heartbeat went stale is ``alive=False`` even if a job row still names it (it likely died).

    Attributes:
        worker_id (str): The worker's stable id (its hostname).
        alive (bool): Its heartbeat is fresher than the liveness threshold.
        busy (bool): It currently owns at least one RUNNING job.
        last_seen (datetime | None): Its last heartbeat tick (None when no heartbeat row exists).
        started_at (datetime | None): When the worker process registered (None when no heartbeat).
        jobs (list[JobStatus]): Its running jobs, live.
    """

    worker_id: str = Field(description="The worker's stable id (its hostname).")
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
    """Every known worker's liveness + running jobs — the monitoring view (idle-alive included)."""

    workers: list[WorkerActivity] = Field(default_factory=list)


class QueueDepth(BaseModel):
    """Backlog counters — pending (queued, unclaimed) and running jobs, fleet-wide or per-collection."""

    pending: int = Field(description="Jobs queued but not yet claimed by a worker.")
    running: int = Field(description="Jobs a worker is currently executing.")


class StageDurations(BaseModel):
    """Average per-stage duration for a collection — the basis for a running job's ETA."""

    collection_id: str = Field(description="The collection the averages were computed over.")
    stage_seconds: dict[str, float] = Field(
        default_factory=dict,
        description="Stage id → average wall-clock seconds over the collection's DONE jobs. The UI "
        "sums the not-yet-completed stages of a running job to estimate its remaining time.",
    )


class CollectionCost(BaseModel):
    """The collection's paid text-gen roll-up — tokens and USD summed over its documents' jobs."""

    collection_id: str = Field(description="The collection totalled.")
    total_prompt_tokens: int = Field(description="Sum of input tokens over the collection's jobs.")
    total_completion_tokens: int = Field(description="Sum of output tokens over the jobs.")
    cost_usd: float = Field(description="Sum of USD cost over the jobs.")
    document_count: int = Field(description="Number of jobs (documents) in the roll-up.")


__all__ = [
    "JobStatus",
    "JobEvent",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "QueueDepth",
    "StageDurations",
    "CollectionCost",
]
