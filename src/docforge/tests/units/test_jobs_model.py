"""JobStatus.from_row — the ``stalled`` derivation + the ``updated_at`` passthrough.

Only a RUNNING job can stall (its ``updated_at`` freezes when progress stops); a RUNNING row idle
past STALLED_AFTER_SECONDS is an EARLY wedge warning the UI shows before the worker reaper hard-fails
it. done/failed/pending are never stalled, however old their ``updated_at`` is.

The router model module is loaded by FILE PATH (it depends only on pydantic + the shared_libs ORM
enum, never on the app runtime), so the test needs neither an app boot nor the services ``.env``.
"""

import importlib.util
import pathlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from shared_libs.services.db.postgresql.tables import JobStatus as JobStatusEnum

_MODELS_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "app"
    / "backend"
    / "routers"
    / "jobs"
    / "models.py"
)


@pytest.fixture(scope="module")
def jobs_models():
    """The loaded router model module (by file path — pydantic + the ORM enum only)."""
    spec = importlib.util.spec_from_file_location("_jobs_models_under_test", _MODELS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def job_model(jobs_models):
    """(JobStatus, STALLED_AFTER_SECONDS) loaded straight from the router model file."""
    return jobs_models.JobStatus, jobs_models.STALLED_AFTER_SECONDS


def _row(status: JobStatusEnum, *, idle_seconds: float) -> SimpleNamespace:
    updated_at = datetime.now(UTC) - timedelta(seconds=idle_seconds)
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        status=status,
        progress=42,
        current_stage="parse",
        error=None,
        attempt=1,
        started_at=updated_at,
        finished_at=None,
        updated_at=updated_at,
        total_prompt_tokens=1200,
        total_completion_tokens=340,
        cost_usd=Decimal("0.123456"),
    )


def test_old_running_job_is_stalled_and_maps_updated_at(job_model) -> None:
    JobStatus, stalled_after = job_model
    row = _row(JobStatusEnum.RUNNING, idle_seconds=stalled_after + 60)

    model = JobStatus.from_row(row)

    assert model.stalled is True
    assert model.updated_at == row.updated_at


def test_recent_running_job_is_not_stalled(job_model) -> None:
    JobStatus, stalled_after = job_model
    row = _row(JobStatusEnum.RUNNING, idle_seconds=stalled_after - 60)

    assert JobStatus.from_row(row).stalled is False


def test_done_job_is_never_stalled_even_when_old(job_model) -> None:
    JobStatus, stalled_after = job_model
    row = _row(JobStatusEnum.DONE, idle_seconds=stalled_after + 3600)

    assert JobStatus.from_row(row).stalled is False


def test_failed_job_is_never_stalled_even_when_old(job_model) -> None:
    JobStatus, stalled_after = job_model
    row = _row(JobStatusEnum.FAILED, idle_seconds=stalled_after + 3600)

    assert JobStatus.from_row(row).stalled is False


def test_pending_job_is_never_stalled(job_model) -> None:
    JobStatus, stalled_after = job_model
    row = _row(JobStatusEnum.PENDING, idle_seconds=stalled_after + 3600)

    assert JobStatus.from_row(row).stalled is False


def test_job_status_maps_the_token_cost_meter(job_model) -> None:
    """The per-document meter columns are surfaced (cost cast Decimal → float for JSON)."""
    JobStatus, _ = job_model
    model = JobStatus.from_row(_row(JobStatusEnum.RUNNING, idle_seconds=1))

    assert model.total_prompt_tokens == 1200
    assert model.total_completion_tokens == 340
    assert model.cost_usd == pytest.approx(0.123456)


def test_job_event_maps_tokens_and_cost(jobs_models) -> None:
    """JobEvent.from_row lifts the per-stage token/cost columns; a NULL cost stays None."""
    JobEvent = jobs_models.JobEvent
    row = SimpleNamespace(
        stage="metagen",
        status="success",
        started_at=None,
        finished_at=None,
        detail="120 ms",
        prompt_tokens=800,
        completion_tokens=210,
        cost_usd=Decimal("0.045000"),
    )

    event = JobEvent.from_row(row)
    assert (event.prompt_tokens, event.completion_tokens) == (800, 210)
    assert event.cost_usd == pytest.approx(0.045)


def test_job_event_null_meter_stays_none(jobs_models) -> None:
    """A stage that made no paid call surfaces None tokens + None cost (not a fabricated 0)."""
    JobEvent = jobs_models.JobEvent
    row = SimpleNamespace(
        stage="chunk",
        status="success",
        started_at=None,
        finished_at=None,
        detail="12 ms",
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
    )

    event = JobEvent.from_row(row)
    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.cost_usd is None
