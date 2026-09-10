"""JobProgressRecorder — the coarse percentage uses the PLANNED-path denominator.

The denominator is the count of stages a successful run actually walks (``planned_stage_ids``), NOT
every top-level node: an escalation/fallback stage that runs only on a bad outcome must not sit in the
denominator, or the percentage is understated for the whole run. When no planned set is supplied the
recorder falls back to every root id (the pre-fix behaviour), so the change is opt-in from the caller.

The recorder's CONTEXT is fully mocked (mirrors test_jobs_usage): only the ``set_progress`` writes are
asserted, for the percentage each root END advances to.
"""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase


@pytest.fixture
def progress_module(worker_jobs_modules):
    """The jobs.progress module (imported under the fake backend by the session fixture)."""
    return sys.modules["jobs.progress"]


def _mock_context() -> tuple[SimpleNamespace, MagicMock]:
    jobs = MagicMock()
    jobs.set_progress = AsyncMock()
    jobs.record_event = AsyncMock()
    jobs.finalize_event = AsyncMock()
    jobs.set_items = AsyncMock()
    jobs.add_usage = AsyncMock()
    return SimpleNamespace(database=SimpleNamespace(jobs=jobs)), jobs


async def _end(recorder, node_id: str) -> None:
    """Fire a bare END (no record → a success stage with no usage) for a root stage."""
    await recorder(
        ProgressEvent(phase=ProgressPhase.END, node_id=node_id, kind="parser", record=None)
    )


def _last_progress(jobs: MagicMock) -> int:
    """The ``progress`` value of the most recent set_progress call."""
    return jobs.set_progress.call_args.kwargs["progress"]


async def test_percentage_uses_planned_denominator_not_all_roots(
    progress_module, monkeypatch
) -> None:
    # 4 top-level roots but only 3 on the planned path (parse_fallback never runs on a good pass).
    context, jobs = _mock_context()
    monkeypatch.setattr(progress_module, "CONTEXT", context)
    recorder = progress_module.JobProgressRecorder(
        uuid.uuid4(),
        ["a", "b", "c", "parse_fallback"],
        planned_stage_ids=["a", "b", "c"],
    )

    await _end(recorder, "a")
    # 1 of 3 planned = 33%. If it wrongly used all 4 roots it would report 25%.
    assert _last_progress(jobs) == 33

    await _end(recorder, "b")
    assert _last_progress(jobs) == 66


async def test_percentage_falls_back_to_all_roots_without_a_plan(
    progress_module, monkeypatch
) -> None:
    # No planned set supplied → denominator is every root id (the pre-fix behaviour, kept for callers
    # that do not compute a plan).
    context, jobs = _mock_context()
    monkeypatch.setattr(progress_module, "CONTEXT", context)
    recorder = progress_module.JobProgressRecorder(uuid.uuid4(), ["a", "b", "c", "d"])

    await _end(recorder, "a")
    assert _last_progress(jobs) == 25  # 1 of 4 roots


async def _run_fanout(recorder, *, total: int, item_count: int) -> None:
    """Drive a full fan-out: arm the counter, then fire item_count body-entry END events + the root END."""
    await recorder(
        ProgressEvent(phase=ProgressPhase.START, node_id="fan", kind="foreach", total_items=total)
    )
    # The body entry's first START binds the entry id the counter keys on.
    await recorder(ProgressEvent(phase=ProgressPhase.START, node_id="body_entry", kind="vlm"))
    for _ in range(item_count):
        await recorder(ProgressEvent(phase=ProgressPhase.END, node_id="body_entry", kind="vlm"))
    await recorder(
        ProgressEvent(phase=ProgressPhase.END, node_id="fan", kind="foreach", record=None)
    )


async def test_fanout_counter_is_throttled_but_final_value_is_exact(
    progress_module, monkeypatch
) -> None:
    # 60 items fan out, but the per-item write is throttled (batch of 25, 1s window) — far fewer than
    # 60 UPDATEs fire, and the EXACT final count is force-written when the fan-out ends.
    context, jobs = _mock_context()
    monkeypatch.setattr(progress_module, "CONTEXT", context)
    recorder = progress_module.JobProgressRecorder(uuid.uuid4(), ["fan"])

    await _run_fanout(recorder, total=60, item_count=60)

    # The throttle collapses 60 per-item writes into a handful (arm + batch crossings + final).
    assert jobs.set_items.await_count < 60
    # The LAST write settles the row on the exact final count, never a stale batch boundary.
    assert jobs.set_items.call_args.args[1:] == (60, 60)


async def test_escalation_root_that_does_run_is_still_traced(progress_module, monkeypatch) -> None:
    # A fallback root excluded from the DENOMINATOR is still in ``_roots`` — if it DOES run, its END
    # opens a trace row and advances progress (capped at 99), never silently dropped.
    context, jobs = _mock_context()
    monkeypatch.setattr(progress_module, "CONTEXT", context)
    recorder = progress_module.JobProgressRecorder(
        uuid.uuid4(), ["a", "parse_fallback"], planned_stage_ids=["a"]
    )

    await _end(recorder, "a")
    await _end(recorder, "parse_fallback")  # ran on escalation: traced, progress pinned at the cap

    assert jobs.record_event.await_count == 2
    assert _last_progress(jobs) == 99  # 2 done over a 1-stage plan, clamped to 99
