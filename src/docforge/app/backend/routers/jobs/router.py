# ====== Code Summary ======
# The jobs router — READ-ONLY ingestion status: the worker writes the job row (running,
# progress per node, done/failed with the error verbatim); the backend only serves it.

# ====== Standard Library Imports ======
import uuid
from collections import defaultdict

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
from .models import JobEvent, JobStatus, JobTrace, WorkerActivity, WorkersLive
from .stream import stream_job_events

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_status(job) -> JobStatus:
    """Map one job row to its polling model (shared by every route here)."""
    return JobStatus.from_row(job)


@router.get("", response_model=list[JobStatus])
@auto_handle_errors
async def list_jobs(
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> list[JobStatus]:
    """
    Return a collection's jobs, newest first — the task table of the monitoring view.

    Returns:
        list[JobStatus]: Every job of the collection with its live state.
    """
    # 1. The collection is a QUERY param, invisible to the path-scope gate — enforce it here.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Straight read — the worker maintains every row.
    jobs = await CONTEXT.database.jobs.list_for_collection(collection_id)
    return [_job_status(job) for job in jobs]


@router.get(
    "/workers/live", response_model=WorkersLive, dependencies=[Depends(require(Capability.READ))]
)
@auto_handle_errors
async def live_workers() -> WorkersLive:
    """
    Return what every worker is doing RIGHT NOW — derived from the RUNNING job rows.

    Returns:
        WorkersLive: Running jobs grouped by worker (empty when the fleet is idle).
    """
    # 1. RUNNING rows carry worker_id + current_stage — that IS the live fleet view.
    running = await CONTEXT.database.jobs.list_active()
    by_worker: dict[str, list] = defaultdict(list)
    for job in running:
        by_worker[job.worker_id or "unknown"].append(_job_status(job))
    return WorkersLive(
        workers=[WorkerActivity(worker_id=w, jobs=jobs) for w, jobs in sorted(by_worker.items())]
    )


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
        stream_job_events(CONTEXT.database.jobs, job_id),
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
        JobStatus: Status, progress, current stage, and the error when failed.
    """
    # 1. The row is the truth — the worker maintains it, we only read.
    job = await CONTEXT.database.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    # 2. No collection in the path — scope the read by the job's own collection.
    AuthzGuard.assert_collection_scope(principal, str(job.collection_id))

    # 3. Serve it as the UI's polling model.
    return _job_status(job)


__all__ = ["router"]
