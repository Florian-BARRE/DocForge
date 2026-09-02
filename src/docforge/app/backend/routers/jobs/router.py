# ====== Code Summary ======
# The jobs router — READ-ONLY ingestion status: the worker writes the job row (running,
# progress per node, done/failed with the error verbatim); the backend only serves it.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
from .helpers import CancelAction, JobCancellationHelpers, WorkersLiveHelpers
from .models import (
    CancelResult,
    CollectionCost,
    JobEvent,
    JobPage,
    JobStatus,
    JobTrace,
    QueueDepth,
    StageDurations,
    WorkersLive,
)
from .stream import stream_job_events

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobPage)
@auto_handle_errors
async def list_jobs(
    collection_id: uuid.UUID,
    limit: int = Query(
        default=RUNTIME_CONFIG.JOBS_MAX_PAGE_SIZE,
        ge=1,
        description="Page size, clamped down to JOBS_MAX_PAGE_SIZE. Defaults to that ceiling.",
    ),
    offset: int = Query(default=0, ge=0, description="Rows to skip for paging."),
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> JobPage:
    """
    Return one page of a collection's jobs, newest first — the task table of the monitoring view.

    A heavily re-ingested collection can hold thousands of job rows, so the list is BOUNDED: ``limit``
    is clamped to ``JOBS_MAX_PAGE_SIZE`` (and defaults to it) and the response carries the total so the
    UI can page. The row join adds the document filename + collection name (no second round-trip).

    Returns:
        JobPage: total + limit/offset echo + the page of jobs.
    """
    # 1. The collection is a QUERY param, invisible to the path-scope gate — enforce it here.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Clamp the page size so a client can never demand an unbounded scan of a huge job table.
    page_size = min(limit, RUNTIME_CONFIG.JOBS_MAX_PAGE_SIZE)

    # 3. One bounded page + the total, under the same collection predicate; the worker maintains every
    #    row and the join carries the display names so the table shows "what is ingesting" in one call.
    total = await CONTEXT.database.jobs.count_for_collection(collection_id)
    jobs = await CONTEXT.database.jobs.list_for_collection_with_names(
        collection_id, page_size, offset
    )
    return JobPage(
        total=total,
        limit=page_size,
        offset=offset,
        jobs=[
            JobStatus.from_row(
                entry.job,
                entry.document_filename,
                entry.collection_name,
                document_title=entry.document_title,
            )
            for entry in jobs
        ],
    )


@router.get("/stage-durations", response_model=StageDurations)
@auto_handle_errors
async def stage_durations(
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> StageDurations:
    """
    Return a collection's average per-stage duration — the basis for a running job's ETA.

    Averaged over the collection's DONE jobs' stage events (only events with both timestamps). The
    UI sums the not-yet-completed stages of a running job to estimate its remaining time.

    Returns:
        StageDurations: Stage id → average wall-clock seconds.
    """
    # 1. Collection is a QUERY param, invisible to the path-scope gate — enforce it here.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. The averages the worker's stage timeline yields for this collection.
    stage_seconds = await CONTEXT.database.jobs.avg_stage_durations(collection_id)
    return StageDurations(collection_id=str(collection_id), stage_seconds=stage_seconds)


@router.get("/cost", response_model=CollectionCost)
@auto_handle_errors
async def collection_cost(
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> CollectionCost:
    """
    Return a collection's paid text-gen roll-up — tokens and USD summed over its documents' jobs.

    Returns:
        CollectionCost: Total prompt/completion tokens, total USD cost, and the document count.
    """
    # 1. Collection is a QUERY param, invisible to the path-scope gate — enforce it here.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Roll up the per-document meters the worker maintained.
    prompt, completion, cost, count = await CONTEXT.database.jobs.collection_cost(collection_id)
    return CollectionCost(
        collection_id=str(collection_id),
        total_prompt_tokens=prompt,
        total_completion_tokens=completion,
        cost_usd=cost,
        document_count=count,
    )


@router.get("/workers/live", response_model=WorkersLive)
@auto_handle_errors
async def live_workers(
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> WorkersLive:
    """
    Return every known worker's liveness + running jobs — the live fleet view.

    Fuses two independent signals so an idle-but-alive worker is visible and a dead one is flagged:
    the worker_heartbeats table drives ``alive`` (a fresh heartbeat), the RUNNING job rows drive
    ``busy`` (owning a job). A worker with a heartbeat but no job appears ``alive=True, busy=False``.

    Tenant isolation: this endpoint is fleet-wide with no ``collection_id`` in the path, so a
    full-access / wildcard key sees every worker's jobs while a collection-scoped key sees worker
    liveness but ONLY its own collections' running jobs — it can never read another tenant's
    job/document/collection ids here.

    Returns:
        WorkersLive: One entry per worker (empty only when no worker has ever heartbeated).
    """
    # 1. Resolve the caller's visible collections BEFORE any DB read (None = unrestricted). This is
    #    the in-memory scope gate for a query-less, fleet-wide endpoint — it may 403 a malformed key.
    allowed = AuthzGuard.scoped_collections(principal)

    # 2. Liveness (heartbeats) + activity (running jobs, joined to their document/collection names)
    #    are two reads; the helper fuses + scopes them and carries the display names through. Pruning
    #    crashed workers is NOT done here — a GET must not fleet-wide DELETE; the worker reaper cron
    #    owns that (worker/backend/libs/jobs/reaper.py), so this read is side-effect-free and a stale
    #    card ages out within one reaper cycle instead of on every poll.
    heartbeats = await CONTEXT.database.jobs.list_heartbeats()
    running = await CONTEXT.database.jobs.list_active_with_names()
    return WorkersLiveHelpers.assemble(heartbeats, running, allowed_collections=allowed)


@router.get("/queue", response_model=QueueDepth)
@auto_handle_errors
async def queue_depth(
    collection_id: uuid.UUID | None = None,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> QueueDepth:
    """
    Return the backlog depth — pending (queued, unclaimed) and running job counts.

    Fleet-wide counts are FULL-ACCESS only: a collection-scoped key must pass a ``collection_id`` (a
    query-less call would otherwise leak the whole fleet's backlog to a single-tenant key). A scoped
    request is gated the same way the list route is.

    Returns:
        QueueDepth: The pending and running counts (both zero when nothing is queued).
    """
    # 1. A scoped request passes the collection-scope gate; a fleet-wide one (no collection_id) is
    #    only allowed for an unrestricted key — a scoped key must name a collection it owns (403 else),
    #    so it can never read cross-tenant fleet totals.
    if collection_id is not None:
        AuthzGuard.assert_collection_scope(principal, str(collection_id))
    elif AuthzGuard.scoped_collections(principal) is not None:
        raise HTTPException(
            status_code=403,
            detail="collection_id is required for a collection-scoped key (fleet-wide counts are "
            "restricted to full-access keys).",
        )

    # 2. One grouped count read yields both numbers.
    pending, running = await CONTEXT.database.jobs.queue_depth(collection_id)
    return QueueDepth(pending=pending, running=running)


@router.get("/{job_id}/events", response_model=JobTrace)
@auto_handle_errors
async def get_job_trace(
    job_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> JobTrace:
    """
    Return the job's per-node execution trace (one entry per stage, in order).

    Returns:
        JobTrace: Stage, status, timestamps and duration/error detail per node.
    """
    # 1. Load the job to derive its collection; unknown id is a 404 (before any scope decision).
    job = await CONTEXT.database.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    # 2. The job carries no collection in the path — scope it by the row's collection.
    AuthzGuard.assert_collection_scope(principal, str(job.collection_id))

    # 3. The trace rows the worker landed at each stage end.
    events = await CONTEXT.database.jobs.list_events(job_id)
    return JobTrace(job_id=str(job_id), events=[JobEvent.from_row(e) for e in events])


@router.get("/{job_id}/stream")
@auto_handle_errors
async def stream_job(
    job_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> StreamingResponse:
    """
    Live Server-Sent Events feed of an ingestion job — pushed as progress lands, closes at terminal.

    Same READ capability + collection-scope gate as the poll routes (the poll endpoints stay). The
    stream is DB-poll-backed (no message bus): it re-reads the job row + stage-event table on a short
    interval and emits only the delta — each new stage event and every status change — until the job
    is done/failed, then closes. Prefer this over polling GET /jobs/{id} for a live UI.

    Returns:
        StreamingResponse: A ``text/event-stream`` of ``data: {...}\\n\\n`` frames. 404 when the job
        is unknown (resolved before the stream opens, so the collection scope can be enforced).
    """
    # 1. Resolve + scope the job BEFORE opening the stream — a 404/403 must be a normal HTTP status,
    #    not an error buried mid-stream once the event-stream response has already started.
    job = await CONTEXT.database.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(job.collection_id))

    # 2. Hand the poll-backed generator the jobs facade; it yields frames until the job terminates.
    return StreamingResponse(
        stream_job_events(
            CONTEXT.database.jobs,
            job_id,
            poll_interval=RUNTIME_CONFIG.SSE_POLL_INTERVAL_SECONDS,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}", response_model=JobStatus)
@auto_handle_errors
async def get_job(
    job_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> JobStatus:
    """
    Return one ingestion job's live state (poll this after an upload).

    Returns:
        JobStatus: Status, progress, current stage, document/collection name, and the error when failed.
    """
    # 1. The row is the truth — the worker maintains it; the join adds the display names.
    entry = await CONTEXT.database.jobs.get_with_names(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    # 2. No collection in the path — scope the read by the job's own collection.
    AuthzGuard.assert_collection_scope(principal, str(entry.job.collection_id))

    # 3. Serve it as the UI's polling model, carrying the joined names.
    return JobStatus.from_row(
        entry.job,
        entry.document_filename,
        entry.collection_name,
        document_title=entry.document_title,
    )


@router.post("/{job_id}/cancel", response_model=CancelResult)
@auto_handle_errors
async def cancel_job(
    job_id: uuid.UUID,
    force: bool = Query(
        default=False,
        description="Immediately CANCEL a running/wedged job regardless of worker state (the manual "
        "force-fail) instead of asking it to stop cooperatively at its next stage boundary.",
    ),
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> CancelResult:
    """
    Stop an ingestion job — cooperatively for a running job, immediately for a queued or wedged one.

    Behaviour by the job's current state:
      * queued (pending) → CANCELLED now; the worker skips it when it dequeues (its arq task id was
        never captured, so it cannot be pulled from the queue) — the document is marked CANCELLED.
      * running, ``force=false`` → a cooperative-cancel flag is raised; the worker's runner stops at
        its next stage boundary and marks job + document CANCELLED. The job stays ``running`` (with
        ``cancel_requested=true``) until it does.
      * running, ``force=true`` → force-terminated NOW (job + document CANCELLED) regardless of the
        worker — the manual reaper for a wedged/infinite job (shares the cron reaper's transition).
      * already terminal (done / failed / cancelled) → 409 (nothing to cancel).

    Returns:
        CancelResult: The job's post-call status, whether a cooperative stop is pending, and the outcome.
    """
    # 1. Resolve the job (404) and scope it by its own collection (403 cross-tenant) BEFORE any
    #    mutation — a scoped key can never cancel another collection's job.
    job = await CONTEXT.database.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(job.collection_id))

    # 2. Decide the action from the current state (pure, no I/O) — an already-terminal job is a 409
    #    before any write, satisfying the fail-fast contract.
    action = JobCancellationHelpers.decide(job.status, force)
    if action == CancelAction.ALREADY_TERMINAL:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is already {job.status.value} — nothing to cancel.",
        )

    # 3. Cooperative stop of a running job: flag it; it winds down at its next stage boundary.
    if action == CancelAction.REQUEST:
        await CONTEXT.database.jobs.request_cancel(job_id)
        CONTEXT.logger.info(f"Cancellation requested for running job {job_id}")
        return CancelResult(
            job_id=str(job_id),
            status="running",
            cancel_requested=True,
            outcome="cancellation_requested",
            detail="Cooperative cancellation requested; the job stops at its next stage boundary.",
        )

    # 4. Queued job, or a forced running/wedged one: terminate immediately (job + document CANCELLED)
    #    through the SAME force-terminate path the cron reaper uses.
    reason = (
        "cancelled while queued (before it ran)"
        if action == CancelAction.TERMINATE
        else "force-terminated while running (wedged-job override)"
    )
    await CONTEXT.database.jobs.force_terminate(job_id, reason=reason)
    CONTEXT.logger.info(f"Cancelled job {job_id} ({action.value}): {reason}")
    return CancelResult(
        job_id=str(job_id),
        status="cancelled",
        cancel_requested=False,
        outcome="cancelled",
        detail=reason,
    )


__all__ = ["router"]
