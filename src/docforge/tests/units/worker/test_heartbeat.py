"""Worker de-registration + crashed-worker pruning (the 'stale off workers accumulate forever' fix).

Three surfaces:
  * HeartbeatWriter.stop — on a CLEAN shutdown it cancels the beat loop AND deletes its own row, so
    the worker vanishes from the fleet immediately; a delete error is best-effort (swallowed).
  * JobsFacade.delete_heartbeat / prune_stale_heartbeats — the orchestration wrappers.
  * JobApi.prune_stale_heartbeats — the PREDICATE: a DB-clock cutoff DELETE ... RETURNING, so a
    crashed worker (no clean shutdown) is removed once it ages past the cutoff.

HeartbeatWriter is flat-importable (worker/backend/libs on sys.path — see the root conftest); it
only imports shared_libs, never the worker's backend package, so no fake-backend dance is needed.
Postgres is fully mocked (same session-yielding stub as the reaper/ingestion-facade tests).
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from heartbeat import HeartbeatWriter
from sqlalchemy.dialects import postgresql

from shared_libs.services.db.facades import JobsFacade
from shared_libs.services.db.facades import jobs_facade as facade_module


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


# --------------------------------------------------------------------------- #
# HeartbeatWriter.stop — clean shutdown de-registers the worker
# --------------------------------------------------------------------------- #


async def test_stop_deletes_its_own_heartbeat_row() -> None:
    """A cleanly-stopped worker removes its own liveness row so it disappears from the fleet."""
    delete_heartbeat = AsyncMock()
    database = SimpleNamespace(jobs=SimpleNamespace(delete_heartbeat=delete_heartbeat))
    writer = HeartbeatWriter(database, worker_id="w1", worker_name="w1", interval_seconds=10)

    writer.start()
    await writer.stop()

    delete_heartbeat.assert_awaited_once_with("w1")


async def test_stop_deletes_even_when_never_started() -> None:
    """stop() de-registers the row regardless of whether the beat loop ever ran."""
    delete_heartbeat = AsyncMock()
    database = SimpleNamespace(jobs=SimpleNamespace(delete_heartbeat=delete_heartbeat))
    writer = HeartbeatWriter(database, worker_id="w1", worker_name="w1", interval_seconds=10)

    await writer.stop()

    delete_heartbeat.assert_awaited_once_with("w1")


async def test_stop_swallows_a_delete_error() -> None:
    """A DB blip during de-registration must never crash an otherwise-clean shutdown."""
    delete_heartbeat = AsyncMock(side_effect=RuntimeError("db down"))
    database = SimpleNamespace(jobs=SimpleNamespace(delete_heartbeat=delete_heartbeat))
    writer = HeartbeatWriter(database, worker_id="w1", worker_name="w1", interval_seconds=10)

    # No exception escapes stop().
    await writer.stop()

    delete_heartbeat.assert_awaited_once_with("w1")


# --------------------------------------------------------------------------- #
# JobsFacade wrappers
# --------------------------------------------------------------------------- #


async def test_facade_delete_heartbeat_delegates_to_the_api(monkeypatch) -> None:
    delete_heartbeat = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "delete_heartbeat", delete_heartbeat)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    await facade.delete_heartbeat("w1")

    assert delete_heartbeat.await_args.args[1] == "w1"


async def test_facade_prune_stale_heartbeats_returns_removed_ids(monkeypatch) -> None:
    prune = AsyncMock(return_value=["w-dead-1", "w-dead-2"])
    monkeypatch.setattr(facade_module.JobApi, "prune_stale_heartbeats", prune)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    removed = await facade.prune_stale_heartbeats(older_than_seconds=180)

    assert removed == ["w-dead-1", "w-dead-2"]
    assert prune.await_args.args[1] == 180


# --------------------------------------------------------------------------- #
# JobApi.prune_stale_heartbeats — the predicate
# --------------------------------------------------------------------------- #


async def test_prune_stale_heartbeats_deletes_on_the_db_clock_and_returns_ids() -> None:
    """The DELETE cuts on now() - interval (never Python's clock) and RETURNs the removed ids."""
    captured: dict[str, object] = {}

    class _CapturingSession:
        async def execute(self, statement):
            captured["statement"] = statement
            result = MagicMock()
            result.scalars.return_value.all.return_value = ["w-dead"]
            return result

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    removed = await JobApi.prune_stale_heartbeats(_CapturingSession(), older_than_seconds=180)

    assert removed == ["w-dead"]
    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    assert "delete from worker_heartbeats" in sql
    # DB clock, not Python: the cutoff is now() minus an interval.
    assert "now()" in sql and "make_interval" in sql
    # The removed ids come back via RETURNING.
    assert "returning" in sql and "worker_id" in sql


async def test_delete_heartbeat_targets_the_worker_row() -> None:
    """delete_heartbeat removes exactly the one worker's row (keyed by worker_id)."""
    captured: dict[str, object] = {}

    class _CapturingSession:
        async def execute(self, statement):
            captured["statement"] = statement
            return MagicMock()

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    await JobApi.delete_heartbeat(_CapturingSession(), worker_id="w1")

    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    assert "delete from worker_heartbeats" in sql
    assert "worker_id" in sql and "'w1'" in sql
