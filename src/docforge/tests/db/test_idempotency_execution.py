"""EXECUTES the idempotency data layer (IdempotencyApi + IdempotencyFacade) against a real Postgres —
the UNIQUE guard (uq_idempotency_key_scope) that a shape-only unit test never triggers, plus the
complete/delete/prune SQL. Covers: a fresh guard insert; a concurrent/duplicate insert raising the
UniqueViolation that the façade translates into a conflict (created=False + the incumbent row);
complete caching the response for replay; delete dropping a row so a retry can re-run; and prune
deleting strictly-expired rows.

Each test opens its own engine/session against the session-scoped migrated throwaway db; the
idempotency table is emptied at the top of each test so the suite is order-independent.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared_libs.services.db.facades import IdempotencyFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import IdempotencyApi
from shared_libs.services.db.postgresql.tables import IdempotencyKey, IdempotencyState

pytestmark = pytest.mark.db

_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_SCOPE = "key:11111111-1111-1111-1111-111111111111"
_METHOD = "POST"
_PATH = "/api/v1/collections"
_KEY = "idem-key-1"
_FP = "a" * 64


@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine + session per test, with the idempotency table emptied first."""
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            await db_session.execute(delete(IdempotencyKey))
            await db_session.commit()
            yield db_session
    finally:
        await engine.dispose()


@pytest.fixture
async def facade(migrated_db_dsn: str, session: AsyncSession) -> AsyncIterator[IdempotencyFacade]:
    """An IdempotencyFacade over a real PostgresClient. Depends on ``session`` so the table is emptied
    first (order-independent), then runs on its own engine (disposed on teardown)."""
    client = PostgresClient(migrated_db_dsn)
    try:
        yield IdempotencyFacade(client)
    finally:
        await client.dispose()


# ── the UNIQUE guard (raw API) ────────────────────────────────────────────────────────────────


async def test_insert_then_duplicate_raises_unique_violation(session) -> None:
    """A second insert on the same (scope, method, path, key) raises the UNIQUE guard violation."""
    await IdempotencyApi.insert_in_progress(
        session,
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        request_fingerprint=_FP,
        expires_at=_NOW + timedelta(hours=24),
    )
    await session.commit()

    with pytest.raises(IntegrityError) as exc:
        await IdempotencyApi.insert_in_progress(
            session,
            actor_scope=_SCOPE,
            method=_METHOD,
            path=_PATH,
            idempotency_key=_KEY,
            request_fingerprint=_FP,
            expires_at=_NOW + timedelta(hours=24),
        )
    # The violated constraint is the named scope guard — the SQLAlchemy asyncpg adapter nests the
    # native asyncpg error (which carries constraint_name) under the wrapper's __cause__.
    native = exc.value.orig.__cause__
    assert getattr(native, "constraint_name", None) == "uq_idempotency_key_scope"
    await session.rollback()


# ── the façade (begin conflict signalling, complete, delete, prune) ─────────────────────────────


async def test_begin_creates_then_conflicts(facade) -> None:
    """First begin wins (created=True); a second returns the incumbent in-progress row (created=False)."""
    first = await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        request_fingerprint=_FP,
        expires_at=_NOW + timedelta(hours=24),
    )
    assert first.created is True
    assert first.record.state == IdempotencyState.in_progress

    second = await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        request_fingerprint="b" * 64,  # a different body — the façade still returns the incumbent
        expires_at=_NOW + timedelta(hours=24),
    )
    # 1. The lost race is signalled, and the incumbent row (its ORIGINAL fingerprint) is returned.
    assert second.created is False
    assert second.record is not None
    assert second.record.request_fingerprint == _FP
    assert second.record.state == IdempotencyState.in_progress


async def test_complete_caches_response_for_replay(facade) -> None:
    """complete flips the record to completed and stores the response bytes for verbatim replay."""
    await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        request_fingerprint=_FP,
        expires_at=_NOW + timedelta(hours=24),
    )
    await facade.complete(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        response_status=201,
        response_body=b'{"id":"x"}',
        response_media_type="application/json",
        completed_at=_NOW,
    )

    record = await facade.get(actor_scope=_SCOPE, method=_METHOD, path=_PATH, idempotency_key=_KEY)
    assert record.state == IdempotencyState.completed
    assert record.response_status == 201
    assert record.response_body == b'{"id":"x"}'
    assert record.response_media_type == "application/json"


async def test_delete_lets_a_retry_reinsert(facade) -> None:
    """delete drops the in-progress row so a subsequent begin wins the insert afresh."""
    await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        request_fingerprint=_FP,
        expires_at=_NOW + timedelta(hours=24),
    )
    await facade.delete(actor_scope=_SCOPE, method=_METHOD, path=_PATH, idempotency_key=_KEY)

    # The row is gone → a retry wins the insert again (created=True), not a 409-conflict.
    retry = await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key=_KEY,
        request_fingerprint=_FP,
        expires_at=_NOW + timedelta(hours=24),
    )
    assert retry.created is True


async def test_prune_deletes_strictly_expired(facade, session) -> None:
    """prune removes rows whose expires_at is before the cutoff, keeping the rest."""
    # Two rows: one already expired, one still live (distinct keys → distinct guard rows).
    await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key="expired",
        request_fingerprint=_FP,
        expires_at=_NOW - timedelta(hours=1),
    )
    await facade.begin(
        actor_scope=_SCOPE,
        method=_METHOD,
        path=_PATH,
        idempotency_key="live",
        request_fingerprint=_FP,
        expires_at=_NOW + timedelta(hours=1),
    )

    deleted = await facade.prune(_NOW)
    assert deleted == 1

    live = await facade.get(actor_scope=_SCOPE, method=_METHOD, path=_PATH, idempotency_key="live")
    gone = await facade.get(
        actor_scope=_SCOPE, method=_METHOD, path=_PATH, idempotency_key="expired"
    )
    assert live is not None and gone is None
