"""EXECUTES the audit data layer (AuditApi + AuditFacade) against a real Postgres — the keyset
ordering (created_at DESC, id DESC), the filter predicates, and the retention prune are all SQL that
a shape-only unit test never runs. Covers: newest-first ordering with the id tiebreaker under a
same-instant burst, keyset paging via the row-value comparison (no skip/dup), the actor/target/
correlation filters + the created_at window, and prune deleting strictly older than a cutoff.

Each test opens its own engine/session against the session-scoped migrated throwaway db; the audit
table is emptied at the top of each test so the suite is order-independent.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared_libs.services.db.postgresql.apis import AuditApi
from shared_libs.services.db.postgresql.tables import AuditLog

pytestmark = pytest.mark.db

_BASE = datetime(2026, 1, 1, tzinfo=UTC)
_KEY_A = uuid.uuid4()
_KEY_B = uuid.uuid4()
_COLL = str(uuid.uuid4())


@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine + session per test, with the audit table emptied first (order-independent)."""
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            await db_session.execute(delete(AuditLog))
            await db_session.commit()
            yield db_session
    finally:
        await engine.dispose()


async def _seed(session: AsyncSession, rows: list[AuditLog]) -> None:
    """Insert explicit-created_at rows so keyset ordering is deterministic, and commit."""
    session.add_all(rows)
    await session.commit()


def _row(
    offset_seconds: int, *, key_id: uuid.UUID = _KEY_A, target_id: str | None = _COLL
) -> AuditLog:
    """One audit row at a fixed created_at offset (explicit so ordering is controlled)."""
    return AuditLog(
        created_at=_BASE + timedelta(seconds=offset_seconds),
        method="POST",
        path="/api/v1/collections/{collection_id}",
        status_code=200,
        actor_key_id=key_id,
        actor_label="k",
        target_type="collection",
        target_id=target_id,
        correlation_id="cid",
        client_ip="203.0.113.1",
    )


async def test_orders_newest_first_with_id_tiebreaker(session) -> None:
    """A same-instant burst orders by created_at DESC then id DESC (stable tiebreak)."""
    # Three rows at the SAME created_at — only the id can order them.
    await _seed(session, [_row(0), _row(0), _row(0)])
    page = await AuditApi.list_page(session, limit=10)
    ids = [r.id for r in page]
    assert ids == sorted(ids, reverse=True)  # strictly descending by id


async def test_keyset_pages_without_skip_or_dup(session) -> None:
    """Walking pages via the (created_at, id) cursor covers every row exactly once."""
    await _seed(session, [_row(i) for i in range(5)])

    first = await AuditApi.list_page(session, limit=2)
    second = await AuditApi.list_page(
        session, limit=2, cursor_created_at=first[-1].created_at, cursor_id=first[-1].id
    )
    third = await AuditApi.list_page(
        session, limit=2, cursor_created_at=second[-1].created_at, cursor_id=second[-1].id
    )

    seen = [r.id for r in first + second + third]
    assert len(first) == 2 and len(second) == 2 and len(third) == 1
    assert len(set(seen)) == 5  # no duplicates across pages
    assert seen == sorted(seen, reverse=True)  # globally newest-first


async def test_filters_by_actor_key(session) -> None:
    await _seed(session, [_row(0, key_id=_KEY_A), _row(1, key_id=_KEY_B), _row(2, key_id=_KEY_A)])
    page = await AuditApi.list_page(session, limit=10, actor_key_id=_KEY_A)
    assert {r.actor_key_id for r in page} == {_KEY_A} and len(page) == 2


async def test_filters_by_target(session) -> None:
    other = str(uuid.uuid4())
    await _seed(session, [_row(0, target_id=_COLL), _row(1, target_id=other)])
    page = await AuditApi.list_page(session, limit=10, target_type="collection", target_id=_COLL)
    assert [r.target_id for r in page] == [_COLL]


async def test_filters_by_created_window(session) -> None:
    await _seed(session, [_row(0), _row(100), _row(200)])
    page = await AuditApi.list_page(
        session,
        limit=10,
        created_from=_BASE + timedelta(seconds=50),
        created_to=_BASE + timedelta(seconds=200),  # exclusive upper bound drops offset=200
    )
    assert [r.created_at for r in page] == [_BASE + timedelta(seconds=100)]


async def test_prune_deletes_strictly_older_than_cutoff(session) -> None:
    await _seed(session, [_row(0), _row(100), _row(200)])
    cutoff = _BASE + timedelta(seconds=100)  # deletes offset=0, keeps 100 (not <) and 200
    deleted = await AuditApi.prune(session, cutoff)
    await session.commit()
    assert deleted == 1
    remaining = await AuditApi.list_page(session, limit=10)
    assert [r.created_at for r in remaining] == [
        _BASE + timedelta(seconds=200),
        _BASE + timedelta(seconds=100),
    ]
