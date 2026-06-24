# ====== Code Summary ======
# Top-level /api/v1/jobs router (Brique A) — global job listing, single-job detail (enriched
# with live arq status), and job cancellation via arq's abort mechanism.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
from arq.jobs import Job
from fastapi import APIRouter, HTTPException, Query

# ====== Internal Project Imports ======
from ...context import CONTEXT
from ...libs.utils.error_handling import auto_handle_errors
from .models import JobCancelResponse, JobListResponse, JobResponse

router = APIRouter(tags=["jobs"])


@router.get("", response_model=JobListResponse)
@auto_handle_errors
async def list_jobs(
    status: str | None = Query(None, description="Filter by job status."),
    collection_id: uuid.UUID | None = Query(None, description="Filter by collection."),
    limit: int = Query(50, ge=1, le=200, description="Page size."),
    offset: int = Query(0, ge=0, description="Page offset."),
) -> JobListResponse:
    """
    List jobs across all collections (newest first), with optional filters.

    Returns:
        JobListResponse: Paginated jobs with the total match count.
    """
    # 1. Query the global job list
    async with CONTEXT.postgres.session() as session:
        jobs, total = await CONTEXT.job_repo.list_jobs(
            session, status=status, collection_id=collection_id, limit=limit, offset=offset,
        )

    # 2. Serialize the page
    return JobListResponse(
        jobs=[JobResponse.from_model(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
@auto_handle_errors
async def get_job(job_id: uuid.UUID) -> JobResponse:
    """
    Fetch a single job, enriched with its live arq-side status.

    Args:
        job_id (uuid.UUID): Job identifier.

    Returns:
        JobResponse: The job with persisted state plus the live arq status.

    Raises:
        HTTPException: 404 when the job does not exist.
    """
    # 1. Load the persisted job row
    async with CONTEXT.postgres.session() as session:
        job = await CONTEXT.job_repo.get_by_id(session, job_id)
    if job is None:
        # 404 — no job row with this id.
        CONTEXT.logger.warning(f"Job lookup rejected (404 unknown job): job={job_id}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    # 2. Attach the live arq status (queued / in_progress / complete / …)
    arq_status = await CONTEXT.queue_introspector.job_arq_status(str(job_id))
    return JobResponse.from_model(job, arq_status=arq_status)


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
@auto_handle_errors
async def cancel_job(job_id: uuid.UUID) -> JobCancelResponse:
    """
    Request cancellation of a queued or running job via arq's abort mechanism.

    A queued job is removed before it starts; a running job receives a cancellation at its next
    await point. Requires ``allow_abort_jobs=True`` on the worker (enabled by default).

    Args:
        job_id (uuid.UUID): Job identifier.

    Returns:
        JobCancelResponse: Whether arq accepted the abort.

    Raises:
        HTTPException: 404 when the job does not exist.
    """
    # 1. Guard against cancelling an unknown job
    async with CONTEXT.postgres.session() as session:
        job = await CONTEXT.job_repo.get_by_id(session, job_id)
    if job is None:
        # 404 — cannot cancel a job that does not exist.
        CONTEXT.logger.warning(f"Job cancel rejected (404 unknown job): job={job_id}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    # 2. Ask arq to abort (job ids match the enqueue-time _job_id = str(job_id))
    aborted = await Job(str(job_id), redis=CONTEXT.arq_pool).abort(timeout=5.0)
    message = (
        "Abort accepted — job cancelled or will stop at the next await point."
        if aborted else
        "Abort not applied — job already finished or could not be cancelled."
    )
    # Cancellation is a state-changing request — record the arq abort outcome.
    CONTEXT.logger.info(f"Job cancel requested job={job_id} aborted={aborted}")
    return JobCancelResponse(job_id=job_id, aborted=aborted, message=message)
