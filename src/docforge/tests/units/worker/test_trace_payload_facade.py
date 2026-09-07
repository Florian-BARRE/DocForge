"""TracePayloadFacade + TracePurgeHelper + the gc_trace_payloads cron — the trace READ/LIFECYCLE half.

All serviceless (Postgres/S3 mocked, the data-access APIs patched on the facade module):
  * read_payload — resolves the row (scoped to the job), then maps a stored ref → the parsed payload,
    a shape-only row → has_full False, an over-cap object → truncated, an unknown row → found False.
  * gc_before — resolves the expired job ids then delegates to purge_jobs (converging retention pass).
  * TracePurgeHelper.purge — clears the DB refs THEN prefix-deletes each job's object-store namespace,
    and is best-effort (a store error is swallowed, never raised — a purge can never fail a delete).
  * gc_trace_payloads — the cron: keep-forever (retention 0) is a no-op; a positive window forwards a cutoff.
"""

import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import trace_payload_facade as facade_module
from shared_libs.services.db.facades import trace_purge as purge_module
from shared_libs.services.db.facades.trace_payload_facade import TracePayloadFacade
from shared_libs.services.db.facades.trace_purge import TracePurgeHelper


def _postgres_yielding(session: MagicMock) -> MagicMock:
    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _s3_yielding(client: object | None = None) -> MagicMock:
    @asynccontextmanager
    async def _client():
        yield client if client is not None else MagicMock()

    s3 = MagicMock()
    s3.client = _client
    s3.bucket = "bucket"
    return s3


def _row(**overrides):
    """A stage-event row stand-in with the trace columns the facade reads."""
    base = dict(
        id=uuid.uuid4(),
        stage="parse",
        node_path="parse",
        input_ref="trace/j/aaa",
        output_ref="trace/j/bbb",
        has_full_input=True,
        has_full_output=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# read_payload
# --------------------------------------------------------------------------- #


async def test_read_payload_returns_parsed_payload_under_cap(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.JobApi, "get_event", AsyncMock(return_value=_row()))
    monkeypatch.setattr(facade_module.S3ObjectApi, "head_size", AsyncMock(return_value=12))
    monkeypatch.setattr(facade_module.S3ObjectApi, "get", AsyncMock(return_value=b'{"k": 1}'))
    facade = TracePayloadFacade(_postgres_yielding(MagicMock()), _s3_yielding())

    result = await facade.read_payload(uuid.uuid4(), uuid.uuid4(), "input", max_bytes=1000)

    assert result.found and result.has_full
    assert result.payload == {"k": 1} and result.size_bytes == 12 and result.truncated is False


async def test_read_payload_shape_only_row_has_no_full(monkeypatch) -> None:
    row = _row(input_ref=None, has_full_input=False)
    monkeypatch.setattr(facade_module.JobApi, "get_event", AsyncMock(return_value=row))
    get = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "get", get)
    facade = TracePayloadFacade(_postgres_yielding(MagicMock()), _s3_yielding())

    result = await facade.read_payload(uuid.uuid4(), uuid.uuid4(), "input", max_bytes=1000)

    assert result.found is True and result.has_full is False
    get.assert_not_awaited()  # a shape-only slot never touches the object store


async def test_read_payload_unknown_row_is_not_found(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.JobApi, "get_event", AsyncMock(return_value=None))
    facade = TracePayloadFacade(_postgres_yielding(MagicMock()), _s3_yielding())

    result = await facade.read_payload(uuid.uuid4(), uuid.uuid4(), "output", max_bytes=1000)
    assert result.found is False


async def test_read_payload_over_cap_is_truncated_without_body(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.JobApi, "get_event", AsyncMock(return_value=_row()))
    monkeypatch.setattr(facade_module.S3ObjectApi, "head_size", AsyncMock(return_value=5000))
    get = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "get", get)
    facade = TracePayloadFacade(_postgres_yielding(MagicMock()), _s3_yielding())

    result = await facade.read_payload(uuid.uuid4(), uuid.uuid4(), "output", max_bytes=1000)

    assert result.has_full is True and result.truncated is True
    assert result.payload is None and result.size_bytes == 5000
    get.assert_not_awaited()  # over-cap: never downloads the body


# --------------------------------------------------------------------------- #
# gc_before + purge_jobs
# --------------------------------------------------------------------------- #


async def test_gc_before_purges_the_expired_jobs(monkeypatch) -> None:
    job_ids = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(
        facade_module.JobApi, "list_trace_job_ids_before", AsyncMock(return_value=job_ids)
    )
    facade = TracePayloadFacade(_postgres_yielding(MagicMock()), _s3_yielding())
    purge = AsyncMock(return_value=7)
    monkeypatch.setattr(facade, "purge_jobs", purge)

    purged = await facade.gc_before(datetime.now(UTC), batch_size=500)

    assert purged == 2
    purge.assert_awaited_once_with(job_ids)


async def test_gc_before_noop_when_nothing_expired(monkeypatch) -> None:
    monkeypatch.setattr(
        facade_module.JobApi, "list_trace_job_ids_before", AsyncMock(return_value=[])
    )
    facade = TracePayloadFacade(_postgres_yielding(MagicMock()), _s3_yielding())
    purge = AsyncMock()
    monkeypatch.setattr(facade, "purge_jobs", purge)

    assert await facade.gc_before(datetime.now(UTC), batch_size=500) == 0
    purge.assert_not_awaited()


async def test_purge_helper_clears_refs_then_prefix_deletes(monkeypatch) -> None:
    job_ids = [uuid.uuid4(), uuid.uuid4()]
    clear = AsyncMock()
    delete_prefix = AsyncMock(return_value=3)
    monkeypatch.setattr(purge_module.JobApi, "clear_trace_refs", clear)
    monkeypatch.setattr(purge_module.S3ObjectApi, "delete_prefix", delete_prefix)

    deleted = await TracePurgeHelper.purge(_postgres_yielding(MagicMock()), _s3_yielding(), job_ids)

    # Refs cleared once (all jobs), and one prefix-delete per job.
    assert deleted == 6
    clear.assert_awaited_once()
    assert clear.await_args.args[1] == job_ids
    assert delete_prefix.await_count == 2


async def test_purge_helper_is_best_effort_on_store_error(monkeypatch) -> None:
    monkeypatch.setattr(purge_module.JobApi, "clear_trace_refs", AsyncMock())
    monkeypatch.setattr(
        purge_module.S3ObjectApi,
        "delete_prefix",
        AsyncMock(side_effect=RuntimeError("s3 down")),
    )
    # A store failure is swallowed (never raised) so a purge can't fail the delete it rides behind.
    deleted = await TracePurgeHelper.purge(
        _postgres_yielding(MagicMock()), _s3_yielding(), [uuid.uuid4()]
    )
    assert deleted == 0


async def test_purge_empty_is_noop(monkeypatch) -> None:
    clear = AsyncMock()
    monkeypatch.setattr(purge_module.JobApi, "clear_trace_refs", clear)
    assert await TracePurgeHelper.purge(_postgres_yielding(MagicMock()), _s3_yielding(), []) == 0
    clear.assert_not_awaited()


# --------------------------------------------------------------------------- #
# gc_trace_payloads — the cron coroutine
# --------------------------------------------------------------------------- #


def _gc_module(worker_jobs_modules):
    _ = worker_jobs_modules  # forces the one-time fake-backend import of the jobs package
    return sys.modules["jobs.trace_gc"]


def _fake_context(*, retention_days: int, gc: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        RUNTIME_CONFIG=SimpleNamespace(
            WORKER_TRACE_RETENTION_DAYS=retention_days, WORKER_TRACE_GC_BATCH_SIZE=500
        ),
        database=SimpleNamespace(trace_payloads=SimpleNamespace(gc_before=gc)),
        logger=MagicMock(),
    )


async def test_gc_cron_purges_when_retention_positive(worker_jobs_modules, monkeypatch) -> None:
    module = _gc_module(worker_jobs_modules)
    gc = AsyncMock(return_value=4)
    monkeypatch.setattr(module, "CONTEXT", _fake_context(retention_days=14, gc=gc))

    result = await module.gc_trace_payloads({})

    assert result == 4
    gc.assert_awaited_once()
    # A cutoff datetime + the batch size are forwarded.
    assert isinstance(gc.await_args.args[0], datetime)
    assert gc.await_args.args[1] == 500


async def test_gc_cron_is_a_noop_when_keep_forever(worker_jobs_modules, monkeypatch) -> None:
    module = _gc_module(worker_jobs_modules)
    gc = AsyncMock(return_value=9)
    monkeypatch.setattr(module, "CONTEXT", _fake_context(retention_days=0, gc=gc))

    assert await module.gc_trace_payloads({}) == 0
    gc.assert_not_awaited()
