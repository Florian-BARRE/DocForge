"""The token/cost meter on the worker side:

  * StageUsageSummer.summarize / JobProgressRecorder.__call__ END — totals a stage's paid usage over
    its WHOLE execution tree (per-figure VLM calls are nested child records), prices MIXED models per
    leaf, lands the summed tokens/cost on the JobStageEvent, and folds the totals into the job
    aggregate via add_usage. A stage with no usage writes NULL columns and never calls add_usage.
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
from shared_libs.pipelines.ingest.estimate import RateTable

# The canonical default rate table — what the meter prices against absent per-collection overrides.
_RATES = RateTable.default()


@pytest.fixture
def progress_module(worker_jobs_modules):
    """The jobs.progress module (imported by the session fixture under the fake backend)."""
    return sys.modules["jobs.progress"]


@pytest.fixture
def usage_module(worker_jobs_modules):
    """The jobs.usage module (StageUsageSummer), imported under the same fake backend."""
    return sys.modules["jobs.usage"]


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
# StageUsageSummer.summarize — the pure recursive helper (moved out of JobProgressRecorder)
# --------------------------------------------------------------------------- #


def test_sum_usage_prices_mixed_models_per_leaf(usage_module) -> None:
    record = _group([_group([_leaf("gpt-4o-mini", 1_000_000, 0), _leaf("gpt-4o", 0, 1_000_000)])])
    prompt, completion, cost, count = usage_module.StageUsageSummer.summarize(record, _RATES)

    assert (prompt, completion, count) == (1_000_000, 1_000_000, 2)
    # gpt-4o-mini input (0.15) + gpt-4o output (10.00) — priced per leaf, not one model per stage.
    assert cost == pytest.approx(0.15 + 10.00)


def test_sum_usage_unknown_model_gives_tokens_but_no_cost(usage_module) -> None:
    record = _group([_leaf("local-model", 100, 50)])
    prompt, completion, cost, count = usage_module.StageUsageSummer.summarize(record, _RATES)

    assert (prompt, completion, count) == (100, 50, 1)
    assert cost is None  # no priceable leaf -> "—", never a fabricated 0


def test_sum_usage_prices_against_a_per_collection_rate_override(usage_module) -> None:
    """The meter prices against the collection's EFFECTIVE table — a per-collection rate override
    changes the metered cost, so actual spend matches the (equally-overridden) estimate (audit 543)."""
    # A collection that negotiated gpt-4o-mini at 1.00/2.00 (vs the default 0.15/0.60).
    rates = RateTable.from_overrides(
        {"rates": {"models": {"gpt-4o-mini": {"input": 1.00, "output": 2.00}}}}
    )
    record = _group([_leaf("gpt-4o-mini", 1_000_000, 1_000_000)])
    _, _, cost, _ = usage_module.StageUsageSummer.summarize(record, rates)

    assert cost == pytest.approx(1.00 + 2.00)  # the OVERRIDE rate, not the 0.15 + 0.60 default


def test_sum_usage_no_usage_is_empty(usage_module) -> None:
    record = _group([_group([])])
    assert usage_module.StageUsageSummer.summarize(record, _RATES) == (0, 0, None, 0)


def _embed_leaf(model: str, prompt: int) -> NodeExecutionRecord:
    """A paid embed leaf: input tokens only (completion is always 0 for an embedding call)."""
    return NodeExecutionRecord(
        node_id="embed",
        kind="embed",
        status=NodeStatus.SUCCESS,
        duration_ms=1.0,
        usage=NodeUsage(model=model, prompt_tokens=prompt, completion_tokens=0),
    )


def _free_leaf() -> NodeExecutionRecord:
    """A local/free embed leaf: it stamps NO usage, so it contributes nothing to the meter."""
    return NodeExecutionRecord(
        node_id="embed", kind="embed", status=NodeStatus.SUCCESS, duration_ms=1.0, usage=None
    )


def test_sum_usage_prices_paid_embed_leaf(usage_module) -> None:
    # text-embedding-3-small = 0.02 USD / 1M input tokens; embeddings have no completion side.
    record = _group([_embed_leaf("text-embedding-3-small", 1_000_000)])
    prompt, completion, cost, count = usage_module.StageUsageSummer.summarize(record, _RATES)

    assert (prompt, completion, count) == (1_000_000, 0, 1)
    assert cost == pytest.approx(0.02)


def test_sum_usage_free_embed_leaf_contributes_nothing(usage_module) -> None:
    record = _group([_free_leaf()])
    assert usage_module.StageUsageSummer.summarize(record, _RATES) == (0, 0, None, 0)


def test_sum_usage_unknown_embed_model_tokens_no_cost(usage_module) -> None:
    record = _group([_embed_leaf("local-embed-model", 4_000)])
    prompt, completion, cost, count = usage_module.StageUsageSummer.summarize(record, _RATES)

    assert (prompt, completion, count) == (4_000, 0, 1)
    assert cost is None  # tokens shown, cost "—"


def _ocr_leaf(kind: str, pages: int) -> NodeExecutionRecord:
    """A paid per-page OCR leaf: pages billed, no tokens (OCR is priced per page, not per token)."""
    return NodeExecutionRecord(
        node_id="ocr",
        kind="ocr",
        status=NodeStatus.SUCCESS,
        duration_ms=1.0,
        usage=NodeUsage(model=kind, prompt_tokens=0, completion_tokens=0, pages=pages),
    )


def _free_ocr_leaf() -> NodeExecutionRecord:
    """A local/free OCR leaf (rapidocr/paddle): stamps NO usage, contributes nothing to the meter."""
    return NodeExecutionRecord(
        node_id="ocr", kind="ocr", status=NodeStatus.SUCCESS, duration_ms=1.0, usage=None
    )


def test_sum_usage_prices_paid_ocr_leaf_per_page_zero_tokens(usage_module) -> None:
    # mistral = 0.004 USD / page; 3 pages → cost = 3 × rate, and OCR contributes 0 tokens.
    record = _group([_ocr_leaf("mistral", 3)])
    prompt, completion, cost, count = usage_module.StageUsageSummer.summarize(record, _RATES)

    assert (prompt, completion, count) == (0, 0, 1)
    assert cost == pytest.approx(3 * 0.004)


def test_sum_usage_free_ocr_leaf_contributes_nothing(usage_module) -> None:
    record = _group([_free_ocr_leaf()])
    assert usage_module.StageUsageSummer.summarize(record, _RATES) == (0, 0, None, 0)


def test_sum_usage_unknown_ocr_kind_pages_no_cost(usage_module) -> None:
    record = _group([_ocr_leaf("some-local-ocr", 5)])
    prompt, completion, cost, count = usage_module.StageUsageSummer.summarize(record, _RATES)

    assert (prompt, completion, count) == (0, 0, 1)  # pages carry no tokens
    assert cost is None  # unknown kind → "—", never fabricated


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
    assert "group by job_stage_event.stage" in sql
    # DONE jobs only, and only events with both timestamps.
    assert "job.status = 'done'" in sql
    assert "job_stage_event.started_at is not null" in sql
    assert "job_stage_event.finished_at is not null" in sql


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
