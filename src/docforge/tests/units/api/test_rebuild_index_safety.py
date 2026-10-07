"""rebuild_index safety refusals: 409 ``rebuild_force_cancel_refused`` for a forced cancel of a running
rebuild on a live worker (allowed on a dead one), 409 ``rebuild_unsupported_chunk_lexical`` at
admission for a legacy chunk-scope lexical field, and 409 ``rebuild_index_active`` on a collection
DELETE while a rebuild runs (facade refuses before cancelling anything). Facades mocked.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_libs.public_models import FieldScope
from shared_libs.services.db.facades import IndexRebuildActiveError, RebuildUnsupportedError
from shared_libs.services.db.postgresql.tables import JobKind, JobStatus

COLLECTION_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _rebuild_job() -> SimpleNamespace:
    return SimpleNamespace(
        id=JOB_ID,
        collection_id=COLLECTION_ID,
        status=JobStatus.RUNNING,
        kind=JobKind.REBUILD_INDEX,
        worker_id="w1",
    )


def _wire_cancel(monkeypatch, heartbeat_age_s: float) -> AsyncMock:
    from backend.context import CONTEXT

    beat = SimpleNamespace(
        worker_id="w1", last_seen=datetime.now(UTC) - timedelta(seconds=heartbeat_age_s)
    )
    force = AsyncMock(return_value=_rebuild_job())
    monkeypatch.setattr(CONTEXT.database.jobs, "get", AsyncMock(return_value=_rebuild_job()))
    monkeypatch.setattr(CONTEXT.database.jobs, "list_heartbeats", AsyncMock(return_value=[beat]))
    monkeypatch.setattr(CONTEXT.database.jobs, "force_terminate", force)
    return force


def test_force_cancel_of_running_rebuild_on_live_worker_is_409(client, monkeypatch) -> None:
    force = _wire_cancel(monkeypatch, heartbeat_age_s=1)

    response = client.post(f"/api/v1/jobs/{JOB_ID}/cancel?force=true")

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "rebuild_force_cancel_refused"
    force.assert_not_awaited()


def test_force_cancel_of_rebuild_on_dead_worker_is_allowed(client, monkeypatch) -> None:
    force = _wire_cancel(monkeypatch, heartbeat_age_s=3600)

    response = client.post(f"/api/v1/jobs/{JOB_ID}/cancel?force=true")

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "cancelled"
    force.assert_awaited_once()


def test_rebuild_with_chunk_lexical_field_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    error = RebuildUnsupportedError(COLLECTION_ID, ["kw"])
    monkeypatch.setattr(CONTEXT.database.index_rebuild, "admit", AsyncMock(side_effect=error))

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/rebuild-index")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rebuild_unsupported_chunk_lexical"
    assert response.json()["detail"]["fields"] == ["kw"]


async def test_admission_refuses_chunk_lexical_schema(monkeypatch) -> None:
    from shared_libs.services.db.facades import index_rebuild_facade as module

    fields = [
        SimpleNamespace(field_name="kw", scope=FieldScope.CHUNK, lexical=True),
        SimpleNamespace(field_name="title", scope=FieldScope.DOCUMENT, lexical=True),
    ]
    monkeypatch.setattr(module.RebuildJobApi, "lock_collection", AsyncMock(return_value=True))
    monkeypatch.setattr(module.RebuildJobApi, "active_rebuild", AsyncMock(return_value=None))
    monkeypatch.setattr(module.CollectionApi, "get_schema", AsyncMock(return_value=fields))

    @asynccontextmanager
    async def _session():
        yield MagicMock()

    facade = module.IndexRebuildFacade(SimpleNamespace(session=_session), MagicMock(), None)
    with pytest.raises(RebuildUnsupportedError) as caught:
        await facade.admit(COLLECTION_ID)
    assert caught.value.fields == ["kw"]


def test_delete_during_rebuild_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    error = IndexRebuildActiveError(COLLECTION_ID, JOB_ID)
    monkeypatch.setattr(CONTEXT.database.collections, "delete", AsyncMock(side_effect=error))

    response = client.delete(f"/api/v1/collections/{COLLECTION_ID}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rebuild_index_active"


async def test_facade_delete_refuses_before_cancelling_anything(monkeypatch) -> None:
    from shared_libs.services.db.facades import collections_facade as module

    monkeypatch.setattr(
        module.RebuildJobApi, "active_rebuild", AsyncMock(return_value=_rebuild_job())
    )
    drop = AsyncMock()
    monkeypatch.setattr(module.QdrantCollectionApi, "drop", drop)

    @asynccontextmanager
    async def _session():
        yield MagicMock()

    facade = module.CollectionsFacade(SimpleNamespace(session=_session), MagicMock(), MagicMock())
    facade._cancel_active_jobs = AsyncMock()
    with pytest.raises(IndexRebuildActiveError):
        await facade.delete(COLLECTION_ID)
    facade._cancel_active_jobs.assert_not_awaited()
    drop.assert_not_awaited()
