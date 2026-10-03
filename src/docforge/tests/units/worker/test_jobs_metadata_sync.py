"""sync_document_metadata — the per-document metadata re-embed arq task drives its PRE-CREATED tracked
job row through the lifecycle so the UI can watch it complete: RUNNING at start, DONE on success,
FAILED (and re-raised) on error. The sync facades themselves are covered elsewhere; here we assert the
job-lifecycle contract only (serviceless — every facade is mocked)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _fake_context(*, meta_points=5, filter_points=5, meta_error: Exception | None = None):
    """A worker CONTEXT whose jobs/meta_vectors/filters facades are AsyncMocks."""
    meta_sync = (
        AsyncMock(side_effect=meta_error)
        if meta_error is not None
        else AsyncMock(return_value=meta_points)
    )
    return SimpleNamespace(
        worker_id="worker-1",
        logger=SimpleNamespace(info=lambda *a, **k: None),
        database=SimpleNamespace(
            jobs=SimpleNamespace(
                mark_running=AsyncMock(),
                mark_done=AsyncMock(),
                mark_failed=AsyncMock(),
            ),
            meta_vectors=SimpleNamespace(sync_document_meta_vectors=meta_sync),
            filters=SimpleNamespace(
                sync_document_filter_payloads=AsyncMock(return_value=filter_points)
            ),
        ),
    )


async def test_success_runs_then_completes_the_tracked_job(jobs_metadata_sync, monkeypatch) -> None:
    context = _fake_context(meta_points=4, filter_points=6)
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)
    document_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())

    result = await jobs_metadata_sync.sync_document_metadata({"job_try": 1}, document_id, job_id)

    assert result == {"meta_points": 4, "filter_points": 6}
    # RUNNING claimed before the work, DONE after it, never FAILED.
    context.database.jobs.mark_running.assert_awaited_once()
    context.database.jobs.mark_done.assert_awaited_once()
    context.database.jobs.mark_failed.assert_not_awaited()
    # The job id is coerced to a UUID for every lifecycle call.
    assert context.database.jobs.mark_running.await_args.args[0] == uuid.UUID(job_id)


async def test_failure_fails_the_tracked_job_and_reraises(jobs_metadata_sync, monkeypatch) -> None:
    context = _fake_context(meta_error=RuntimeError("qdrant down"))
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)
    document_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())

    with pytest.raises(RuntimeError, match="qdrant down"):
        await jobs_metadata_sync.sync_document_metadata({}, document_id, job_id)

    # Marked FAILED with the error type, never DONE; the raise lets arq account the attempt.
    context.database.jobs.mark_failed.assert_awaited_once()
    assert context.database.jobs.mark_failed.await_args.kwargs["error_type"] == "RuntimeError"
    context.database.jobs.mark_done.assert_not_awaited()
