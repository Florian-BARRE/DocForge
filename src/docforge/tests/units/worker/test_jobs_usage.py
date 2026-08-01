"""The token/cost meter on the worker side:

  * JobProgressRecorder._sum_usage / __call__ END — totals a stage's paid usage over its WHOLE
    execution tree (per-figure VLM calls are nested child records), prices MIXED models per leaf,
    lands the summed tokens/cost on the JobStageEvent, and folds the totals into the job aggregate
    via add_usage. A stage with no usage writes NULL columns and never calls add_usage.
  * JobApi.avg_stage_durations / collection_cost — the query SHAPE (compiled SQL), mirroring the
    reaper test's statement-compilation style.

The recorder's CONTEXT is fully mocked; Postgres is a capturing session for the query-shape checks.
"""

import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus, NodeUsage
from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase


@pytest.fixture
def progress_module(worker_jobs_modules):
    """The jobs.progress module (imported by the session fixture under the fake backend)."""
    return sys.modules["jobs.progress"]


def _leaf(model: str, prompt: int, completion: int) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_id="leaf",
        kind="vlm",
        status=NodeStatus.SUCCESS,
        duration_ms=1.0,
        usage=NodeUsage(model=model, prompt_tokens=prompt, completion_tokens=completion),
    )


def _group(children: list[NodeExecutionRecord]) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_id="group", kind="group", status=NodeStatus.SUCCESS, duration_ms=1.0, children=children
    )


def _mock_context() -> tuple[SimpleNamespace, MagicMock]:
    jobs = MagicMock()
    jobs.set_progress = AsyncMock()
    jobs.record_event = AsyncMock()
    jobs.add_usage = AsyncMock()
    return SimpleNamespace(database=SimpleNamespace(jobs=jobs)), jobs


async def _run_end(progress_module, monkeypatch, record: NodeExecutionRecord) -> MagicMock:
    """Fire one END event for a root stage carrying ``record`` and return the jobs mock."""
    context, jobs = _mock_context()
    monkeypatch.setattr(progress_module, "CONTEXT", context)
    recorder = progress_module.JobProgressRecorder(uuid.uuid4(), ["stage"])
    await recorder(
        ProgressEvent(phase=ProgressPhase.END, node_id="stage", kind="group", record=record)
    )
    return jobs


# --------------------------------------------------------------------------- #
# _sum_usage — the pure recursive helper
# --------------------------------------------------------------------------- #


def test_sum_usage_prices_mixed_models_per_leaf(progress_module) -> None:
    record = _group([_group([_leaf("gpt-4o-mini", 1_000_000, 0), _leaf("gpt-4o", 0, 1_000_000)])])
    prompt, completion, cost, count = progress_module.JobProgressRecorder._sum_usage(record)

    assert (prompt, completion, count) == (1_000_000, 1_000_000, 2)
    # gpt-4o-mini input (0.15) + gpt-4o output (10.00) — priced per leaf, not one model per stage.
    assert cost == pytest.approx(0.15 + 10.00)


def test_sum_usage_unknown_model_gives_tokens_but_no_cost(progress_module) -> None:
    record = _group([_leaf("local-model", 100, 50)])
    prompt, completion, cost, count = progress_module.JobProgressRecorder._sum_usage(record)

    assert (prompt, completion, count) == (100, 50, 1)
    assert cost is None  # no priceable leaf -> "—", never a fabricated 0


def test_sum_usage_no_usage_is_empty(progress_module) -> None:
    record = _group([_group([])])
    assert progress_module.JobProgressRecorder._sum_usage(record) == (0, 0, None, 0)


# --------------------------------------------------------------------------- #
# recorder END — persists tokens/cost + folds into the job aggregate
# --------------------------------------------------------------------------- #


async def test_end_lands_summed_usage_and_calls_add_usage(progress_module, monkeypatch) -> None:
    record = _group([_leaf("gpt-4o-mini", 1_000_000, 0), _leaf("gpt-4o", 0, 1_000_000)])
    jobs = await _run_end(progress_module, monkeypatch, record)

    event = jobs.record_event.call_args.args[0]
    assert event.prompt_tokens == 1_000_000
    assert event.completion_tokens == 1_000_000
    assert event.cost_usd == Decimal(str(0.15 + 10.00))

    jobs.add_usage.assert_awaited_once()
    _job_id, prompt, completion, cost = jobs.add_usage.call_args.args
    assert (prompt, completion) == (1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 10.00)


async def test_end_without_usage_writes_null_and_skips_add_usage(
    progress_module, monkeypatch
) -> None:
    jobs = await _run_end(progress_module, monkeypatch, _group([_group([])]))

    event = jobs.record_event.call_args.args[0]
    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.cost_usd is None
    jobs.add_usage.assert_not_awaited()


async def test_end_unpriced_model_records_tokens_with_null_cost(
    progress_module, monkeypatch
) -> None:
    jobs = await _run_end(progress_module, monkeypatch, _group([_leaf("local-model", 100, 50)]))

    event = jobs.record_event.call_args.args[0]
    assert (event.prompt_tokens, event.completion_tokens) == (100, 50)
    assert event.cost_usd is None  # unpriced -> tokens shown, cost "—"
    # Still folded into the aggregate (tokens count, cost None adds 0).
    jobs.add_usage.assert_awaited_once()
    assert jobs.add_usage.call_args.args[3] is None


# --------------------------------------------------------------------------- #
# JobApi query shapes
# --------------------------------------------------------------------------- #


class _CapturingSession:
    """Captures the compiled statement; returns a canned scalar result."""

    def __init__(self, one_row: tuple | None = None) -> None:
        self.statement = None
        self._one_row = one_row

    async def execute(self, statement):
        self.statement = statement
        result = MagicMock()
        result.all.return_value = []
        if self._one_row is not None:
            result.one.return_value = self._one_row
        return result


def _sql(session: _CapturingSession) -> str:
    return str(
        session.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()


async def test_avg_stage_durations_query_shape() -> None:
    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    session = _CapturingSession()
    await JobApi.avg_stage_durations(session, uuid.uuid4())

    sql = _sql(session)
    assert "avg(" in sql and "extract(epoch from" in sql
    assert "group by" in sql and "job_stage_event.stage" in sql
    # DONE jobs only, and only events with both timestamps.
    assert "done" in sql
    assert "started_at is not null" in sql and "finished_at is not null" in sql


async def test_collection_cost_query_shape_and_unpack() -> None:
    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    session = _CapturingSession(one_row=(120, 30, Decimal("1.5"), 4))
    result = await JobApi.collection_cost(session, uuid.uuid4())

    assert result == (120, 30, 1.5, 4)
    sql = _sql(session)
    assert "coalesce(sum(job.total_prompt_tokens)" in sql
    assert "coalesce(sum(job.total_completion_tokens)" in sql
    assert "coalesce(sum(job.cost_usd)" in sql
    assert "count(job.id)" in sql
