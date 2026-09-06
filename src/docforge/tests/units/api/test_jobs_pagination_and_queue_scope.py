"""Jobs router hardening: bounded list pagination + fleet-wide queue-depth scope.

Two audit fixes:
  * GET /jobs is paginated — ``limit`` is clamped to JOBS_MAX_PAGE_SIZE (a heavily re-ingested
    collection can hold thousands of rows), and the bounded page is what the facade is asked for.
  * GET /jobs/queue fleet-wide counts (no collection_id) are FULL-ACCESS only — a collection-scoped
    key must name a collection it owns, else a 403 (it can never read cross-tenant backlog totals).

CONTEXT.database is mocked; ``from backend...`` imports are deferred until the ``fastapi_app`` fixture
has registered app/ on sys.path (see tests/units/api/conftest.py).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

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


# ── GET /jobs — pagination clamp ─────────────────────────────────────────────────────────────────


async def test_list_jobs_clamps_limit_to_the_ceiling(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    list_page = AsyncMock(return_value=[])
    jobs = SimpleNamespace(
        list_jobs_with_names=list_page,
        count_jobs=AsyncMock(return_value=4200),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    # A client demands an unbounded page; the server clamps it to the ceiling.
    result = await list_jobs(
        collection_id=uuid.UUID(COLL_A),
        status=None,
        order="newest",
        limit=99_999,
        offset=10,
        principal=_full(),
    )

    ceiling = RUNTIME_CONFIG.JOBS_MAX_PAGE_SIZE
    assert result.limit == ceiling
    assert result.offset == 10
    assert result.total == 4200
    # The facade is asked for exactly the clamped page (never the unbounded scan the client requested).
    list_page.assert_awaited_once_with(
        collection_id=uuid.UUID(COLL_A),
        statuses=None,
        limit=ceiling,
        offset=10,
        newest_first=True,
    )


# ── GET /jobs — fleet-wide scope + status filter + FIFO order ────────────────────────────────────


async def test_list_jobs_fleetwide_denied_for_scoped_key(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    jobs = SimpleNamespace(
        list_jobs_with_names=AsyncMock(return_value=[]),
        count_jobs=AsyncMock(return_value=0),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    # No collection_id = a fleet-wide listing; a collection-scoped key may not read cross-tenant rows.
    with pytest.raises(HTTPException) as exc:
        await list_jobs(collection_id=None, status=None, order="newest", principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # The scope gate fires BEFORE any fleet-wide read.
    jobs.list_jobs_with_names.assert_not_called()
    jobs.count_jobs.assert_not_called()


async def test_list_jobs_fleetwide_status_filter_and_fifo_for_full_key(
    fastapi_app, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    list_page = AsyncMock(return_value=[])
    jobs = SimpleNamespace(
        list_jobs_with_names=list_page,
        count_jobs=AsyncMock(return_value=7),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    # A full-access key lists the whole fleet's PENDING backlog in FIFO (oldest-first) order — the
    # "what runs next" view: no collection scope, a status filter, order=oldest.
    result = await list_jobs(
        collection_id=None,
        status=["pending"],
        order="oldest",
        limit=50,
        offset=0,
        principal=_full(),
    )

    assert result.total == 7
    # collection_id threads through as None (fleet-wide); the status literals map to the enum; and
    # order=oldest selects the FIFO (created_at ASC) sort the pending-backlog view needs.
    list_page.assert_awaited_once_with(
        collection_id=None,
        statuses=[JobStatus.PENDING],
        limit=50,
        offset=0,
        newest_first=False,
    )
    jobs.count_jobs.assert_awaited_once_with(None, [JobStatus.PENDING])


# ── GET /jobs/queue — fleet-wide scope ───────────────────────────────────────────────────────────


async def test_queue_depth_fleetwide_denied_for_scoped_key(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import queue_depth  # noqa: PLC0415

    depth = AsyncMock(return_value=(0, 0))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(queue_depth=depth))
    )

    # A scoped key asking for fleet-wide counts (no collection_id) is a 403 BEFORE any DB read.
    with pytest.raises(HTTPException) as exc:
        await queue_depth(collection_id=None, principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    depth.assert_not_awaited()


async def test_queue_depth_fleetwide_allowed_for_full_access(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import queue_depth  # noqa: PLC0415

    depth = AsyncMock(return_value=(3, 1))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(queue_depth=depth))
    )

    result = await queue_depth(collection_id=None, principal=_full())

    assert (result.pending, result.running) == (3, 1)
    depth.assert_awaited_once_with(None)


async def test_queue_depth_scoped_key_owned_collection_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import queue_depth  # noqa: PLC0415

    depth = AsyncMock(return_value=(2, 0))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(queue_depth=depth))
    )

    result = await queue_depth(collection_id=uuid.UUID(COLL_A), principal=_scoped(COLL_A))

    assert (result.pending, result.running) == (2, 0)
    depth.assert_awaited_once_with(uuid.UUID(COLL_A))


async def test_queue_depth_scoped_key_foreign_collection_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import queue_depth  # noqa: PLC0415

    depth = AsyncMock(return_value=(0, 0))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(queue_depth=depth))
    )

    with pytest.raises(HTTPException) as exc:
        await queue_depth(collection_id=uuid.UUID(COLL_B), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    depth.assert_not_awaited()
