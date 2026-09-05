"""JobApi.mark_running — the per-attempt reset of a job's OBSERVABILITY residue.

A fresh attempt (or any manual re-enqueue that reaches mark_running on a non-terminal row) must wipe
the PREVIOUS attempt's structured failure breadcrumb (failed node id/kind/item + error type) AND the
fan-out item counter, so a re-run that then succeeds never surfaces a stale failed-node trace or an old
items-done/total. The terminal guard is also exercised: a job that is already terminal is never
re-opened (and so its breadcrumb is left intact — the guard wins over the reset).

JobApi is pure shared_libs (no app boot, no services .env): the job row is a plain namespace and the
session is a stub whose ``get`` returns it, so the test asserts on the mutated attributes directly.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.tables import JobStatus


class _StubSession:
    """Minimal async session: ``get`` returns the preset job row; ``execute`` is unused here."""

    def __init__(self, job: SimpleNamespace) -> None:
        self._job = job

    async def get(self, _model: object, _pk: uuid.UUID) -> SimpleNamespace:
        return self._job


def _failed_job(status: JobStatus) -> SimpleNamespace:
    """A job row carrying a full failure breadcrumb + fan-out counter from a prior attempt."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        worker_id="old-worker",
        attempt=1,
        started_at=None,
        finished_at=datetime.now(UTC),
        error="boom at parse",
        current_stage="parse",
        progress=42,
        cancel_requested=True,
        failed_node_id="parse_1",
        failed_node_kind="parser",
        failed_item_index=3,
        error_type="TimeoutError",
        items_done=5,
        items_total=10,
    )


async def test_mark_running_clears_prior_breadcrumb_and_counter_on_fresh_attempt() -> None:
    # A non-terminal row still carrying a prior attempt's breadcrumb + counter is claimed afresh.
    job = _failed_job(JobStatus.PENDING)
    session = _StubSession(job)

    await JobApi.mark_running(
        session, job.id, worker_id="new-worker", attempt=2, started_at=datetime.now(UTC)
    )

    # The claim took, and every prior-attempt residue is wiped clean.
    assert job.status == JobStatus.RUNNING
    assert job.error is None and job.finished_at is None
    assert job.cancel_requested is False
    assert job.failed_node_id is None and job.failed_node_kind is None
    assert job.failed_item_index is None and job.error_type is None
    assert job.items_done is None and job.items_total is None


async def test_failed_then_rerun_to_done_has_cleared_breadcrumb() -> None:
    # A job that failed AT A NODE is re-run: mark_running (fresh attempt) clears the breadcrumb, and a
    # subsequent mark_done leaves it cleared — so a DONE re-run never looks like it failed at a node.
    job = _failed_job(JobStatus.PENDING)
    session = _StubSession(job)

    await JobApi.mark_running(
        session, job.id, worker_id="w", attempt=2, started_at=datetime.now(UTC)
    )
    await JobApi.mark_done(session, job.id, finished_at=datetime.now(UTC))

    assert job.status == JobStatus.DONE
    assert job.failed_node_id is None and job.failed_node_kind is None
    assert job.failed_item_index is None and job.error_type is None
    assert job.items_done is None and job.items_total is None


async def test_mark_running_no_ops_on_a_terminal_job_and_keeps_breadcrumb() -> None:
    # The terminal guard wins: a FAILED row is never resurrected, so its breadcrumb is left intact
    # (breadcrumbs are only ever written on a terminal FAILED job — the reset above is defensive
    # completeness for a non-terminal re-claim, never a path that erases a live terminal outcome).
    job = _failed_job(JobStatus.FAILED)
    session = _StubSession(job)

    await JobApi.mark_running(
        session, job.id, worker_id="w", attempt=2, started_at=datetime.now(UTC)
    )

    assert job.status == JobStatus.FAILED
    assert job.failed_node_id == "parse_1" and job.failed_node_kind == "parser"
    assert job.items_done == 5 and job.items_total == 10
