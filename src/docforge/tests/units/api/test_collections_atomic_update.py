"""V8 write-atomicity: a collection PATCH applies EVERY DB part in ONE transaction.

Before this, the router applied contract / schema / config / overrides as separate facade calls, each
in its own session — a mid-sequence failure left a half-patched collection (e.g. contract renamed but
schema not). ``CollectionsFacade.apply_update`` now threads a SINGLE session through all the parts, so
any failure rolls the WHOLE patch back. These pin the transaction semantics with a session mock that
mirrors ``PostgresClient.session`` exactly (commit on clean exit, rollback + re-raise on error) — the
Qdrant reconcile/backfill deliberately stays OUT of this transaction (it is the router's post-commit
best-effort step, covered by test_collections_schema_reconcile)."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_libs.services.db.facades import CollectionUpdateSpec
from shared_libs.services.db.facades import collections_facade as cf_module
from shared_libs.services.db.facades.collections_facade import CollectionsFacade


class _TrackingSession:
    """Records whether the transaction committed or rolled back (the atomicity proof)."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _postgres_tx(session: _TrackingSession) -> MagicMock:
    """A postgres mock whose session() mirrors PostgresClient.session: commit on clean exit,
    rollback + re-raise on any exception — so a mid-transaction failure is a real rollback."""

    @asynccontextmanager
    async def _session():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _facade(session: _TrackingSession) -> CollectionsFacade:
    return CollectionsFacade(_postgres_tx(session), MagicMock(), MagicMock())


async def test_mid_sequence_failure_rolls_the_whole_patch_back(monkeypatch) -> None:
    """A failure AFTER an earlier part has written leaves the collection fully UNCHANGED: the whole
    transaction rolls back (no commit), so the already-staged contract write never persists."""
    # 1. The contract update succeeds and is recorded; the schema diff then blows up (get_schema).
    monkeypatch.setattr(cf_module.DatabaseHelpers, "validate_vector_slugs", lambda _fields: None)
    contract_update = AsyncMock()
    monkeypatch.setattr(cf_module.CollectionApi, "update", contract_update)
    monkeypatch.setattr(
        cf_module.CollectionApi,
        "get_schema",
        AsyncMock(side_effect=RuntimeError("schema read boom")),
    )
    session = _TrackingSession()
    facade = _facade(session)
    collection_id = uuid.uuid4()

    spec = CollectionUpdateSpec(
        contract_touched=True,
        name="renamed",
        schema_fields=[],  # not None → triggers the (failing) schema diff AFTER the contract write
    )

    # 2. The failure propagates — and the transaction rolled back, never committed.
    with pytest.raises(RuntimeError, match="schema read boom"):
        await facade.apply_update(collection_id, spec)

    assert session.committed is False  # nothing persisted
    assert session.rolled_back is True  # the whole patch was undone
    # 3. The contract write DID run before the failure — proof it shared the rolled-back transaction
    #    (so it leaves no partial effect), not a separate already-committed one.
    contract_update.assert_awaited_once()
    assert contract_update.await_args.args[0] is session


async def test_all_parts_commit_in_one_transaction(monkeypatch) -> None:
    """The happy path stages contract + schema + config + overrides on ONE session and commits once —
    every constituent write receives the SAME session object."""
    # 1. Stub every CollectionApi write; config snapshot needs a collection + a version scalar.
    monkeypatch.setattr(cf_module.DatabaseHelpers, "validate_vector_slugs", lambda _fields: None)
    update = AsyncMock()
    set_overrides = AsyncMock()
    monkeypatch.setattr(cf_module.CollectionApi, "update", update)
    monkeypatch.setattr(cf_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    # The config snapshot locks the collection row FOR UPDATE before minting the next version.
    monkeypatch.setattr(
        cf_module.CollectionApi,
        "get_for_update",
        AsyncMock(return_value=SimpleNamespace(pipeline={"p": 1}, search={})),
    )
    monkeypatch.setattr(cf_module.CollectionApi, "max_config_version", AsyncMock(return_value=3))
    monkeypatch.setattr(cf_module.CollectionApi, "add_config_version", AsyncMock())
    monkeypatch.setattr(cf_module.CollectionApi, "set_estimate_overrides", set_overrides)
    session = _TrackingSession()
    facade = _facade(session)
    collection_id = uuid.uuid4()

    spec = CollectionUpdateSpec(
        contract_touched=True,
        name="c",
        schema_fields=[],
        config_touched=True,
        pipeline={"p": 1},
        embed_reindex=True,
        note="edit",
        apply_overrides=True,
        estimate_overrides={"rate": 1},
    )

    result = await facade.apply_update(collection_id, spec)

    # 2. Exactly one commit, no rollback; the schema part ran; the overrides write shared the session.
    assert session.committed is True
    assert session.rolled_back is False
    assert result.schema_applied is True
    set_overrides.assert_awaited_once()
    assert set_overrides.await_args.args[0] is session


async def test_rename_unique_race_maps_to_duplicate_name_error(monkeypatch) -> None:
    """A rename that loses the uq_collection_name race at commit surfaces as the domain
    DuplicateCollectionNameError (the router turns it into a 409), not a raw IntegrityError → 500 —
    parity with create's own race handling. The transaction still rolls back."""
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    monkeypatch.setattr(cf_module.DatabaseHelpers, "validate_vector_slugs", lambda _fields: None)
    # The contract rename write trips the UNIQUE constraint; _is_duplicate_name confirms it's the name.
    monkeypatch.setattr(
        cf_module.CollectionApi,
        "update",
        AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("uq_collection_name"))),
    )
    monkeypatch.setattr(CollectionsFacade, "_is_duplicate_name", staticmethod(lambda _e: True))
    session = _TrackingSession()
    facade = _facade(session)

    with pytest.raises(cf_module.DuplicateCollectionNameError):
        await facade.apply_update(
            uuid.uuid4(), CollectionUpdateSpec(contract_touched=True, name="taken")
        )

    assert session.committed is False
    assert session.rolled_back is True


async def test_bad_schema_slugs_422_before_any_write(monkeypatch) -> None:
    """A vector-slug collision fails fast BEFORE the transaction opens — no session, no partial
    write (the router maps the ValueError to a 422)."""
    monkeypatch.setattr(
        cf_module.DatabaseHelpers,
        "validate_vector_slugs",
        MagicMock(side_effect=ValueError("slug collision")),
    )
    update = AsyncMock()
    monkeypatch.setattr(cf_module.CollectionApi, "update", update)
    session = _TrackingSession()
    facade = _facade(session)

    with pytest.raises(ValueError, match="slug collision"):
        await facade.apply_update(uuid.uuid4(), CollectionUpdateSpec(schema_fields=[]))

    assert session.committed is False
    assert session.rolled_back is False  # the session was never even entered
    update.assert_not_awaited()
