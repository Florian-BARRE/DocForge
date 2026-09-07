"""GET /jobs/{job_id}/events/{event_id}/payload — the full execution-trace payload fetch route.

Serviceless (CONTEXT.database mocked): the route resolves the job (404/403 gate like the other job
routes), then delegates to ``database.trace_payloads.read_payload`` and maps its ``TracePayloadRead``
to 200 / typed 404. Covered: the happy path (a stored ref → the payload), the two typed 404s (unknown
row, shape-summary-only), the truncated-over-cap case, and the collection-scope gate (403 cross-tenant,
404 unknown job) firing before any read.

``from backend...`` imports are deferred until the ``fastapi_app`` fixture registers app/ on sys.path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from shared_libs.services.db.facades import TracePayloadRead

COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


def _principal(*, permissions):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=permissions, revoked_at=None, user_id="user-1")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _scoped(collection_id: str):
    return _principal(permissions={"capabilities": ["read"], "collections": [collection_id]})


def _full():
    return _principal(permissions=None)


def _job(collection_id: str):
    return SimpleNamespace(id=uuid.uuid4(), collection_id=uuid.UUID(collection_id))


def _wire(monkeypatch, *, job, read_result):
    """Point CONTEXT.database at jobs.get + trace_payloads.read_payload; return the read mock."""
    from backend.context import CONTEXT  # noqa: PLC0415

    read_payload = AsyncMock(return_value=read_result)
    database = SimpleNamespace(
        jobs=SimpleNamespace(get=AsyncMock(return_value=job)),
        trace_payloads=SimpleNamespace(read_payload=read_payload),
    )
    monkeypatch.setattr(CONTEXT, "database", database, raising=False)
    return read_payload


async def test_payload_returns_the_stored_payload(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import get_event_payload  # noqa: PLC0415

    job = _job(COLL_A)
    event_id = uuid.uuid4()
    result = TracePayloadRead(
        found=True,
        has_full=True,
        stage="parse",
        node_path="parse",
        payload={"blocks": [1, 2, 3]},
        size_bytes=42,
    )
    read = _wire(monkeypatch, job=job, read_result=result)

    model = await get_event_payload(
        job_id=job.id, event_id=event_id, slot="output", principal=_scoped(COLL_A)
    )

    assert model.payload == {"blocks": [1, 2, 3]}
    assert (model.slot, model.stage, model.node_path) == ("output", "parse", "parse")
    assert model.truncated is False and model.size_bytes == 42
    # The read is capped and addressed by (job, event, slot).
    read.assert_awaited_once()
    assert read.await_args.args[:3] == (job.id, event_id, "output")


async def test_shape_only_row_is_typed_404(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import get_event_payload  # noqa: PLC0415

    job = _job(COLL_A)
    _wire(monkeypatch, job=job, read_result=TracePayloadRead(found=True, has_full=False))

    with pytest.raises(HTTPException) as exc:
        await get_event_payload(
            job_id=job.id, event_id=uuid.uuid4(), slot="input", principal=_scoped(COLL_A)
        )
    assert exc.value.status_code == 404
    assert "shape summary only" in exc.value.detail


async def test_unknown_event_row_is_404(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import get_event_payload  # noqa: PLC0415

    job = _job(COLL_A)
    _wire(monkeypatch, job=job, read_result=TracePayloadRead(found=False))

    with pytest.raises(HTTPException) as exc:
        await get_event_payload(
            job_id=job.id, event_id=uuid.uuid4(), slot="input", principal=_scoped(COLL_A)
        )
    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail


async def test_over_cap_payload_is_truncated_no_body(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import get_event_payload  # noqa: PLC0415

    job = _job(COLL_A)
    result = TracePayloadRead(
        found=True,
        has_full=True,
        stage="embed",
        node_path="embed",
        truncated=True,
        size_bytes=9_000_000,
    )
    _wire(monkeypatch, job=job, read_result=result)

    model = await get_event_payload(
        job_id=job.id, event_id=uuid.uuid4(), slot="output", principal=_scoped(COLL_A)
    )
    assert model.truncated is True and model.payload is None and model.size_bytes == 9_000_000


async def test_unknown_job_is_404_before_any_read(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import get_event_payload  # noqa: PLC0415

    read = _wire(monkeypatch, job=None, read_result=TracePayloadRead(found=False))

    with pytest.raises(HTTPException) as exc:
        await get_event_payload(
            job_id=uuid.uuid4(), event_id=uuid.uuid4(), slot="input", principal=_full()
        )
    assert exc.value.status_code == 404
    read.assert_not_awaited()


async def test_cross_tenant_is_403_before_any_read(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import get_event_payload  # noqa: PLC0415

    job = _job(COLL_B)
    read = _wire(monkeypatch, job=job, read_result=TracePayloadRead(found=True, has_full=True))

    with pytest.raises(HTTPException) as exc:
        await get_event_payload(
            job_id=job.id, event_id=uuid.uuid4(), slot="input", principal=_scoped(COLL_A)
        )
    assert exc.value.status_code == 403
    read.assert_not_awaited()
