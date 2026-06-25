# ====== Code Summary ======
# Pydantic request/response models for the top-level /api/v1/jobs router (Brique A).
# Jobs are global (not collection-scoped), so this router lives at the API root.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """
    A single ingestion job with its execution telemetry.

    Attributes:
        id (uuid.UUID): Job identifier.
        document_id (uuid.UUID): Document the job processes.
        collection_id (uuid.UUID): Owning collection.
        status (str): Persisted status (pending|running|done|failed).
        error (str | None): Error message when failed.
        created_at (datetime): Admission time.
        worker_id (str | None): Worker process that ran the job.
        started_at (datetime | None): Execution start.
        finished_at (datetime | None): Execution end.
        attempt (int): arq retry attempt number.
        current_stage (str | None): Stage currently executing.
        progress (int): Coarse completion percent (0–100).
        arq_status (str | None): Live arq-side status, when requested for a single job.
    """

    id: uuid.UUID = Field(..., description="Job identifier.")
    document_id: uuid.UUID = Field(..., description="Document the job processes.")
    collection_id: uuid.UUID = Field(..., description="Owning collection.")
    status: str = Field(..., description="Persisted job status.")
    error: str | None = Field(None, description="Error message when failed.")
    created_at: datetime = Field(..., description="Admission time.")
    worker_id: str | None = Field(None, description="Worker process that ran the job.")
    started_at: datetime | None = Field(None, description="Execution start.")
    finished_at: datetime | None = Field(None, description="Execution end.")
    attempt: int = Field(1, description="arq retry attempt number.")
    current_stage: str | None = Field(None, description="Stage currently executing.")
    progress: int = Field(0, description="Coarse completion percent (0–100).")
    arq_status: str | None = Field(None, description="Live arq-side status (single-job view).")

    @classmethod
    def from_model(cls, job: Any, *, arq_status: str | None = None) -> JobResponse:
        """
        Build a response from a JobModel ORM row.

        Args:
            job (Any): JobModel instance.
            arq_status (str | None): Optional live arq status to attach.

        Returns:
            JobResponse: Serializable job view.
        """
        return cls(
            id=job.id,
            document_id=job.document_id,
            collection_id=job.collection_id,
            status=job.status,
            error=job.error,
            created_at=job.created_at,
            worker_id=job.worker_id,
            started_at=job.started_at,
            finished_at=job.finished_at,
            attempt=job.attempt,
            current_stage=job.current_stage,
            progress=job.progress,
            arq_status=arq_status,
        )


class JobListResponse(BaseModel):
    """Paginated list of jobs (newest first)."""

    jobs: list[JobResponse] = Field(..., description="Page of jobs, newest first.")
    total: int = Field(..., description="Total jobs matching the filter.")
    limit: int = Field(..., description="Page size.")
    offset: int = Field(..., description="Page offset.")


class JobCancelResponse(BaseModel):
    """Result of a job cancellation request."""

    job_id: uuid.UUID = Field(..., description="The job that was asked to cancel.")
    aborted: bool = Field(..., description="True if arq accepted the abort.")
    message: str = Field(..., description="Human-readable outcome.")


# ------------------- Public API ------------------- #
__all__ = ["JobResponse", "JobListResponse", "JobCancelResponse"]
