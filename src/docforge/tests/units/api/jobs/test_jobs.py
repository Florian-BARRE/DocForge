# ====== Code Summary ======
# API tests for the /api/v1/jobs router: global listing, single-job detail (with live arq
# status), cancellation, and the 404 paths.

# ====== Standard Library Imports ======
from __future__ import annotations

import datetime
import importlib
import types
import uuid
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Internal Project Imports ======
from backend.context import CONTEXT


def make_job_orm(**overrides: object) -> types.SimpleNamespace:
    """Return a JobModel-like object covering every field JobResponse reads."""
    return types.SimpleNamespace(
        id=overrides.get("id", uuid.uuid4()),
        document_id=overrides.get("document_id", uuid.uuid4()),
        collection_id=overrides.get("collection_id", uuid.uuid4()),
        status=overrides.get("status", "running"),
        error=overrides.get("error", None),
        budget_spent=overrides.get("budget_spent", 0.0),
        created_at=overrides.get("created_at", datetime.datetime.now(datetime.timezone.utc)),
        worker_id=overrides.get("worker_id", "host:1:abcd"),
        started_at=overrides.get("started_at", None),
        finished_at=overrides.get("finished_at", None),
        attempt=overrides.get("attempt", 1),
        current_stage=overrides.get("current_stage", None),
        progress=overrides.get("progress", 0),
    )


class TestListJobs:
    """GET /api/v1/jobs"""

    @pytest.mark.asyncio
    async def test_returns_page_with_total(self, client: httpx.AsyncClient) -> None:
        """Listing returns the serialized page and the total count."""
        job = make_job_orm(status="done", progress=100)
        CONTEXT.job_repo.list_jobs = AsyncMock(return_value=([job], 1))

        response = await client.get("/api/v1/jobs")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["jobs"]) == 1
        assert body["jobs"][0]["status"] == "done"
        assert body["jobs"][0]["progress"] == 100

    @pytest.mark.asyncio
    async def test_passes_filters_to_repo(self, client: httpx.AsyncClient) -> None:
        """Query filters are forwarded to the repository."""
        CONTEXT.job_repo.list_jobs = AsyncMock(return_value=([], 0))
        await client.get("/api/v1/jobs?status=failed&limit=10&offset=5")
        _, kwargs = CONTEXT.job_repo.list_jobs.call_args
        assert kwargs["status"] == "failed"
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5


class TestGetJob:
    """GET /api/v1/jobs/{job_id}"""

    @pytest.mark.asyncio
    async def test_returns_job_with_live_arq_status(self, client: httpx.AsyncClient) -> None:
        """Single-job detail attaches the live arq status."""
        job = make_job_orm()
        CONTEXT.job_repo.get_by_id = AsyncMock(return_value=job)
        CONTEXT.queue_introspector.job_arq_status = AsyncMock(return_value="in_progress")

        response = await client.get(f"/api/v1/jobs/{job.id}")
        assert response.status_code == 200
        assert response.json()["arq_status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_unknown_job_returns_404(self, client: httpx.AsyncClient) -> None:
        """A missing job yields 404."""
        CONTEXT.job_repo.get_by_id = AsyncMock(return_value=None)
        response = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
        assert response.status_code == 404


class TestCancelJob:
    """POST /api/v1/jobs/{job_id}/cancel"""

    @pytest.mark.asyncio
    async def test_abort_accepted(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cancellable job returns aborted=True."""
        job = make_job_orm()
        CONTEXT.job_repo.get_by_id = AsyncMock(return_value=job)

        class FakeJob:
            def __init__(self, job_id: str, redis: object = None) -> None: ...
            async def abort(self, timeout: float | None = None) -> bool:
                return True

        # Patch the module object directly: the package re-exports `router`, which shadows the
        # `backend.routers.jobs.router` name for monkeypatch's string-based path resolution.
        jobs_router_mod = importlib.import_module("backend.routers.jobs.router")
        monkeypatch.setattr(jobs_router_mod, "Job", FakeJob)
        response = await client.post(f"/api/v1/jobs/{job.id}/cancel")
        assert response.status_code == 200
        assert response.json()["aborted"] is True

    @pytest.mark.asyncio
    async def test_cancel_unknown_job_returns_404(self, client: httpx.AsyncClient) -> None:
        """Cancelling a missing job yields 404."""
        CONTEXT.job_repo.get_by_id = AsyncMock(return_value=None)
        response = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/cancel")
        assert response.status_code == 404
