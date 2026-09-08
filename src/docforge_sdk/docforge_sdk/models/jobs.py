# ====== Code Summary ======
# Response models for the jobs resource, mirrored field-for-field from the DocForge backend router
# models: the live ingestion status, one node of the execution trace, the full trace, and the live
# per-worker activity view.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

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
        document_title (str | None): The document's metagen-generated title, joined at read — a
            nicer display label than the filename when present (None if none was generated or the
            document is gone; the UI falls back to document_filename).
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
        error_type (str | None): Structured cause of the failure — usually the raising exception's
            class name (e.g. "TimeoutError"), plus the reaper's attributed "worker_killed" (process
            lost — crash/OOM) and "budget_exceeded" (a stage wedged past the budget on a live worker).
    """

    job_id: str = Field(description="The job row's UUID.")
    document_id: str = Field(description="The document being ingested.")
    document_filename: str | None = Field(
        default=None,
        description="The document's filename, joined at read (None if the document is gone).",
    )
    document_title: str | None = Field(
        default=None,
        description="The document's metagen-generated title, joined at read — a nicer display label "
        "than the filename when present (None if none was generated or the document is gone; the UI "
        "falls back to document_filename).",
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
        default=None,
        description=(
            "Structured cause of the failure. Usually the raising exception's class name (e.g. "
            "'TimeoutError'); the reaper also attributes 'worker_killed' (the worker process was "
            "lost — crash/OOM-kill) and 'budget_exceeded' (a stage wedged past the job's time budget "
            "on a live worker). Set only on a failed job."
        ),
    )


class JobPage(BaseModel):
    """
    One paginated page of jobs (a collection's, or the fleet's) — the response of ``GET /jobs``.

    The list is served bounded (the server clamps ``limit`` to its ceiling) so a heavily re-ingested
    collection — or the fleet-wide "All Jobs" view — never dumps thousands of rows at once. Iterate
    ``jobs`` for the page; read ``total`` to drive a pager.

    Attributes:
        total (int): Total jobs matching the filter (ignores paging — drives the pager).
        limit (int): The applied page size (after the server ceiling clamp).
        offset (int): The applied offset.
        jobs (list[JobStatus]): The page of jobs, in the requested order (newest first by default).
    """

    total: int = Field(
        description="Total jobs matching the filter (ignores paging — drives the pager)."
    )
    limit: int = Field(description="The applied page size (after the server ceiling clamp).")
    offset: int = Field(description="The applied offset.")
    jobs: list[JobStatus] = Field(
        description="The page of jobs, in the requested order (newest first by default)."
    )


class JobEvent(BaseModel):
    """
    One node of the job's execution trace — written by the worker.

    The trace is the FULL per-node execution tree: root stages carry live status/timing/usage, and
    every nested node (group children, per-item ForEach body instances) is persisted after the run.
    The list stays FLAT — the UI rebuilds the tree from ``node_path`` + ``depth`` + ``parent_path``.

    Attributes:
        stage (str): The pipeline node id (the node's own id segment).
        status (str): success / failed / skipped.
        node_kind (str | None): The stage's structural kind (action/group/foreach) or the node's
            concrete kind — None for rows written before this column landed.
        started_at (datetime | None): Node start.
        finished_at (datetime | None): Node end.
        detail (str | None): Duration, or the error when failed.
        prompt_tokens (int | None): Prompt tokens billed by this stage; null when none.
        completion_tokens (int | None): Completion tokens billed; null when none.
        cost_usd (float | None): USD cost; null when no usage or unknown price.
        score (float | None): Quality score in [0, 1] of a scored-family node; null otherwise.
        node_path (str | None): Materialized tree path (root = bare id, nested = dotted); null legacy.
        depth (int | None): Tree depth (0 = root stage); null for legacy rows.
        parent_path (str | None): Parent node's node_path; null for roots and legacy rows.
        item_index (int | None): ForEach item index when inside a fan-out; null otherwise.
    """

    stage: str = Field(description="The pipeline node id (the node's own id segment).")
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
    score: float | None = Field(
        default=None,
        description="Quality score in [0, 1] of a scored-family node (parser/ocr/…), what a "
        "ScoreBelow edge compares to its threshold. None for non-scored nodes and legacy rows.",
    )
    node_path: str | None = Field(
        default=None,
        description="Materialized path of this node in the execution tree — root = bare node id, "
        "nested = dotted path (e.g. 'enrich.figures[3].vlm'). None for legacy rows (pre-tree).",
    )
    depth: int | None = Field(
        default=None,
        description="Depth in the execution tree: 0 = root stage, larger = more nested. None for "
        "legacy rows (the UI treats it as 0).",
    )
    parent_path: str | None = Field(
        default=None,
        description="node_path of this node's parent — None for root stages and legacy rows.",
    )
    item_index: int | None = Field(
        default=None,
        description="Zero-based ForEach item index when this node runs inside a fan-out; None "
        "outside any fan-out (and for legacy rows).",
    )
    event_id: str = Field(
        description="The stage-event row's UUID — the stable handle the full-payload fetch route "
        "addresses (GET /jobs/{job_id}/events/{event_id}/payload)."
    )
    input_summary: dict[str, Any] | None = Field(
        default=None,
        description="Bounded SHAPE descriptor of the node's resolved input (type/fields/sizes/hash) "
        "— never the raw content. None when trace capture was off, the node had no input, or for "
        "legacy rows.",
    )
    output_summary: dict[str, Any] | None = Field(
        default=None,
        description="Bounded SHAPE descriptor of the node's output — never the raw content. None "
        "when trace capture was off, the node produced nothing, or for legacy rows.",
    )
    has_full_input: bool | None = Field(
        default=None,
        description="Whether a FULL raw input payload was stored in the object store (the opt-in "
        "full tier) and can be fetched via the payload route. None/false both mean unavailable.",
    )
    has_full_output: bool | None = Field(
        default=None,
        description="Whether a FULL raw output payload was stored and can be fetched via the payload "
        "route. None/false both mean unavailable.",
    )


class JobEventPayload(BaseModel):
    """
    One stage-event's FULL raw input or output payload, fetched on demand from the object store.

    The trace list (``JobEvent``) carries only the cheap shape summaries; the FULL raw payload of a
    node (stored only when the collection opted into ``trace_verbosity='full'``) is served one slot at
    a time by ``GET /jobs/{job_id}/events/{event_id}/payload?slot=input|output``. The stored payload is
    the node's resolved JSON, so ``payload`` is an arbitrary JSON value.

    Attributes:
        job_id (str): The job the traced node belongs to.
        event_id (str): The stage-event row's UUID the payload was read from.
        slot (str): Which side was fetched: 'input' or 'output'.
        stage (str): The node's stage id (its own id segment) — a display label.
        node_path (str | None): The node's materialized tree path (None for legacy rows).
        truncated (bool): True when the stored object exceeds the read cap: ``payload`` is then None
            and only ``size_bytes`` describes it.
        size_bytes (int): The stored payload object's size in bytes.
        payload (Any): The node's full raw payload (arbitrary JSON), or None when truncated.
    """

    job_id: str = Field(description="The job the traced node belongs to.")
    event_id: str = Field(description="The stage-event row's UUID the payload was read from.")
    slot: str = Field(description="Which side was fetched: 'input' or 'output'.")
    stage: str = Field(description="The node's stage id (its own id segment) — a display label.")
    node_path: str | None = Field(
        default=None,
        description="The node's materialized tree path (None for legacy rows without one).",
    )
    truncated: bool = Field(
        description="True when the stored object exceeds the read cap (or was stored past the "
        "capture cap): ``payload`` is then None and only ``size_bytes`` describes it."
    )
    size_bytes: int = Field(description="The stored payload object's size in bytes.")
    payload: Any = Field(
        default=None,
        description="The node's full raw payload (arbitrary JSON), or None when truncated past the "
        "read cap.",
    )


class JobTrace(BaseModel):
    """
    A job's full per-node execution tree, flat — the UI rebuilds the tree from node_path/depth.

    Attributes:
        job_id (str): The traced job.
        events (list[JobEvent]): Every node of the run, flat and pre-order.
    """

    job_id: str = Field(description="The traced job.")
    events: list[JobEvent] = Field(
        default_factory=list,
        description="Every node of the run, flat and pre-order (parent before children, ForEach "
        "items by index) — the UI nests them via node_path/depth.",
    )


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


class QueueDepth(BaseModel):
    """Backlog counters — pending (queued, unclaimed) and running jobs, fleet-wide or per-collection."""

    pending: int = Field(description="Jobs queued but not yet claimed by a worker.")
    running: int = Field(description="Jobs a worker is currently executing.")


class StageDurations(BaseModel):
    """Average per-stage wall-clock for a collection — the basis for a running job's ETA."""

    collection_id: str = Field(description="The collection the averages were computed over.")
    stage_seconds: dict[str, float] = Field(
        default_factory=dict, description="Stage id → average wall-clock seconds over DONE jobs."
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
    "JobPage",
    "JobEvent",
    "JobEventPayload",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "CancelResult",
    "QueueDepth",
    "StageDurations",
    "CollectionCost",
]
