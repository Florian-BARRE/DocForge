# ====== Code Summary ======
# Unit tests for JobRepository observability write methods (mark_running / mark_finished /
# update_progress) — focuses on the stamping/clamping logic, with get_by_id stubbed.

# ====== Standard Library Imports ======
from __future__ import annotations

import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.storage.postgres.repositories.job_repo import JobRepository


def _fake_job() -> types.SimpleNamespace:
    """A mutable stand-in for a JobModel row."""
    return types.SimpleNamespace(
        status="pending", worker_id=None, attempt=1, started_at=None,
        finished_at=None, current_stage=None, progress=0, error=None, budget_spent=0.0,
    )


@pytest.fixture
def repo() -> JobRepository:
    return JobRepository()


class TestMarkRunning:
    """JobRepository.mark_running"""

    @pytest.mark.asyncio
    async def test_stamps_worker_and_start(self, repo: JobRepository) -> None:
        """Running transition records worker id, attempt and start time, resetting progress."""
        job = _fake_job()
        repo.get_by_id = AsyncMock(return_value=job)  # type: ignore[method-assign]
        session = AsyncMock()
        now = datetime.now(timezone.utc)

        await repo.mark_running(session, uuid.uuid4(), worker_id="w1", attempt=2, started_at=now)

        assert job.status == "running"
        assert job.worker_id == "w1"
        assert job.attempt == 2
        assert job.started_at == now
        assert job.progress == 0
        session.flush.assert_awaited()


class TestMarkFinished:
    """JobRepository.mark_finished"""

    @pytest.mark.asyncio
    async def test_done_sets_progress_100(self, repo: JobRepository) -> None:
        """A done job reads back as 100% with a finish time."""
        job = _fake_job()
        repo.get_by_id = AsyncMock(return_value=job)  # type: ignore[method-assign]
        now = datetime.now(timezone.utc)

        await repo.mark_finished(AsyncMock(), uuid.uuid4(), "done", finished_at=now)

        assert job.status == "done"
        assert job.finished_at == now
        assert job.progress == 100

    @pytest.mark.asyncio
    async def test_failed_records_error_without_forcing_progress(self, repo: JobRepository) -> None:
        """A failed job stores the error and is not bumped to 100%."""
        job = _fake_job()
        job.progress = 55
        repo.get_by_id = AsyncMock(return_value=job)  # type: ignore[method-assign]

        await repo.mark_finished(
            AsyncMock(), uuid.uuid4(), "failed",
            finished_at=datetime.now(timezone.utc), error="boom",
        )

        assert job.status == "failed"
        assert job.error == "boom"
        assert job.progress == 55


class TestUpdateProgress:
    """JobRepository.update_progress"""

    @pytest.mark.asyncio
    async def test_clamps_progress_to_100(self, repo: JobRepository) -> None:
        """Out-of-range progress is clamped into [0, 100]."""
        job = _fake_job()
        repo.get_by_id = AsyncMock(return_value=job)  # type: ignore[method-assign]

        await repo.update_progress(AsyncMock(), uuid.uuid4(), "s4", 150)

        assert job.current_stage == "s4"
        assert job.progress == 100

    @pytest.mark.asyncio
    async def test_missing_job_is_noop(self, repo: JobRepository) -> None:
        """Updating a vanished job logs a warning and does not raise."""
        repo.get_by_id = AsyncMock(return_value=None)  # type: ignore[method-assign]
        await repo.update_progress(AsyncMock(), uuid.uuid4(), "s4", 10)  # no exception
