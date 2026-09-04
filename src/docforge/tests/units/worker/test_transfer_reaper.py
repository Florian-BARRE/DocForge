"""Stuck-transfer reaper cron — fail collection_transfer rows a worker crash left RUNNING forever.

  * reap_stuck_transfers — the CRON coroutine: honours WORKER_REAP_ENABLED, forwards the configured
    staleness horizon to the tracker facade, and returns the reaped ids as strings.

The facade's reap_stale is stubbed (it has its own tests); this pins the cron's flag-gate + wiring.
"""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _reaper_module(worker_jobs_modules):
    """The jobs.transfer_reaper module (imported as a side effect of worker_jobs_modules)."""
    _ = worker_jobs_modules  # forces the one-time fake-backend import of the jobs package
    return sys.modules["jobs.transfer_reaper"]


def _fake_context(*, enabled: bool, reap: AsyncMock, horizon: int = 10800) -> SimpleNamespace:
    return SimpleNamespace(
        RUNTIME_CONFIG=SimpleNamespace(
            WORKER_REAP_ENABLED=enabled, WORKER_TRANSFER_REAP_STALE_SECONDS=horizon
        ),
        database=SimpleNamespace(transfer_tracker=SimpleNamespace(reap_stale=reap)),
        logger=MagicMock(),
    )


async def test_reaper_cron_reaps_and_returns_ids_when_enabled(
    worker_jobs_modules, monkeypatch
) -> None:
    module = _reaper_module(worker_jobs_modules)
    reaped = [uuid.uuid4(), uuid.uuid4()]
    reap = AsyncMock(return_value=reaped)
    monkeypatch.setattr(module, "CONTEXT", _fake_context(enabled=True, reap=reap, horizon=10800))

    result = await module.reap_stuck_transfers({})

    # The configured horizon is forwarded, and the reaped ids come back as strings.
    reap.assert_awaited_once_with(10800)
    assert result == [str(transfer_id) for transfer_id in reaped]


async def test_reaper_cron_is_a_noop_when_disabled(worker_jobs_modules, monkeypatch) -> None:
    module = _reaper_module(worker_jobs_modules)
    reap = AsyncMock(return_value=[uuid.uuid4()])
    monkeypatch.setattr(module, "CONTEXT", _fake_context(enabled=False, reap=reap))

    result = await module.reap_stuck_transfers({})

    assert result == []
    reap.assert_not_awaited()
