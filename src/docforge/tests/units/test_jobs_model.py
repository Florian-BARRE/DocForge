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
def job_model():
    """(JobStatus, STALLED_AFTER_SECONDS) loaded straight from the router model file."""
    spec = importlib.util.spec_from_file_location("_jobs_models_under_test", _MODELS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JobStatus, module.STALLED_AFTER_SECONDS


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
