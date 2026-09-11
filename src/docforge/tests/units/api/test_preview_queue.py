"""QueueClient.get_preview_result — the poll mapping from arq job state to the coarse preview status.

The preview job keeps its result in Redis; this maps the arq JobStatus (+ the stored JobResult) to the
``(status, result_dict | None, error | None)`` the poll endpoint returns. A completed successful job
yields the PreviewResponse dict; a not-yet-terminal job yields pending/running with no result; an
unknown/expired id yields not_found; a hard-crashed job (success=False) yields failed with the reason.
"""

import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

_APP_DIR = str(pathlib.Path(__file__).resolve().parents[3] / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from arq.jobs import JobStatus  # noqa: E402

from backend.utils import queue as queue_mod  # noqa: E402


def _client_with_fake_job(monkeypatch, status, info):
    """Build a QueueClient whose arq Job returns the given status + result_info."""
    client = queue_mod.QueueClient("redis://localhost:6379")
    client._pool = object()  # non-None so __get_pool short-circuits (no real connection)
    fake_job = SimpleNamespace(
        status=AsyncMock(return_value=status),
        result_info=AsyncMock(return_value=info),
    )
    monkeypatch.setattr(queue_mod, "Job", lambda preview_id, pool: fake_job)
    return client


@pytest.mark.asyncio
async def test_poll_done_returns_result(monkeypatch):
    """A complete successful job maps to ('done', <report dict>, None)."""
    report = {"ok": True, "chunk_count": 3}
    client = _client_with_fake_job(
        monkeypatch, JobStatus.complete, SimpleNamespace(success=True, result=report)
    )
    status, result, error = await client.get_preview_result("p1")
    assert (status, result, error) == ("done", report, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job_status,expected",
    [
        (JobStatus.queued, "pending"),
        (JobStatus.deferred, "pending"),
        (JobStatus.in_progress, "running"),
    ],
)
async def test_poll_non_terminal(monkeypatch, job_status, expected):
    """Queued/deferred → pending, in-progress → running, with no result yet."""
    client = _client_with_fake_job(monkeypatch, job_status, None)
    status, result, error = await client.get_preview_result("p2")
    assert status == expected
    assert result is None


@pytest.mark.asyncio
async def test_poll_not_found(monkeypatch):
    """An unknown/expired id is not_found."""
    client = _client_with_fake_job(monkeypatch, JobStatus.not_found, None)
    status, result, error = await client.get_preview_result("gone")
    assert status == "not_found"


@pytest.mark.asyncio
async def test_poll_crashed_job_is_failed(monkeypatch):
    """A completed-but-unsuccessful job (hard crash/timeout) maps to failed with the reason."""
    boom = RuntimeError("worker killed")
    client = _client_with_fake_job(
        monkeypatch, JobStatus.complete, SimpleNamespace(success=False, result=boom)
    )
    status, result, error = await client.get_preview_result("p3")
    assert status == "failed"
    assert result is None
    assert "worker killed" in error
