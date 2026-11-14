# ====== Code Summary ======
# CHARACTERIZATION of the worker's arq settings under the DEFAULT configuration: the cron jobs (count,
# name, minute-set, run-at-startup, per-cron timeout and tries), ``max_jobs``, ``retry_jobs`` and the
# worker-level ``job_timeout`` as a golden — plus the config switches that add or remove crons. The REAL
# ``worker/backend/app.py`` runs; the config is the defaults read statically from runtime_config.py.
# Protects the planned WorkerCron refactor: any drift in cadence, phase offsets or limits fails here.

# ====== Third-Party Library Imports ======
import pytest
from arq.worker import func

# (cron name, minute set, run_at_startup) — the minute sets are ``(offset + k * interval) % 60``.
_DEFAULT_CRONS = [
    ("reap_stuck_jobs", list(range(2, 60, 5)), True),
    ("reap_stuck_transfers", list(range(2, 60, 5)), True),
    ("gc_expired_transfers", [8, 23, 38, 53], False),
    ("gc_idempotency_keys", [35], False),
    ("gc_artifact_cache", [50], False),
    ("gc_trace_payloads", [44], False),
]


def _crons(settings) -> list[tuple[str, list[int], bool]]:
    return [
        (cron.name.removeprefix("cron:"), sorted(cron.minute), cron.run_at_startup)
        for cron in settings.cron_jobs
    ]


def test_default_config_registers_six_crons_with_their_phase_shifted_minute_sets(
    load_worker_app,
) -> None:
    settings = load_worker_app().create_worker_settings()

    assert _crons(settings) == _DEFAULT_CRONS


def test_only_the_reaper_family_runs_at_startup(load_worker_app) -> None:
    settings = load_worker_app().create_worker_settings()

    assert [cron.name for cron in settings.cron_jobs if cron.run_at_startup] == [
        "cron:reap_stuck_jobs",
        "cron:reap_stuck_transfers",
    ]


def test_every_default_cron_fires_at_second_zero_of_its_minutes_with_one_try_and_no_own_timeout(
    load_worker_app,
) -> None:
    settings = load_worker_app().create_worker_settings()

    for cron in settings.cron_jobs:
        assert (cron.hour, cron.second, cron.microsecond) == (None, 0, 123456)
        assert cron.max_tries == 1
        assert cron.timeout_s is None  # no per-cron cap: the worker-level job_timeout applies


def test_no_two_default_gc_crons_share_a_minute_with_the_reaper_or_each_other(
    load_worker_app,
) -> None:
    settings = load_worker_app().create_worker_settings()

    families = {name: set(minutes) for name, minutes, _ in _crons(settings)}
    reaper = families["reap_stuck_jobs"]
    gcs = [minutes for name, minutes in families.items() if name.startswith("gc_")]

    assert all(reaper.isdisjoint(minutes) for minutes in gcs)
    assert sum(len(minutes) for minutes in gcs) == len(set().union(*gcs))


def test_default_worker_limits_are_two_jobs_no_retry_and_the_hard_ceiling_plus_grace(
    load_worker_app,
) -> None:
    settings = load_worker_app().create_worker_settings()

    assert settings.max_jobs == 2
    assert settings.retry_jobs is False
    assert settings.job_timeout == 7200.0 + 60.0
    assert settings.health_check_interval == 30


def test_default_worker_wires_the_lifecycle_hooks_and_the_redis_dsn(load_worker_app) -> None:
    settings = load_worker_app().create_worker_settings()

    assert settings.on_startup.__name__ == "_startup_stub"
    assert settings.on_shutdown.__name__ == "_shutdown_stub"
    assert (settings.redis_settings.host, settings.redis_settings.port) == ("localhost", 6379)


def test_every_cron_function_is_wrapped_so_arq_still_sees_the_original_name(
    load_worker_app,
) -> None:
    settings = load_worker_app().create_worker_settings()

    for cron in settings.cron_jobs:
        assert hasattr(cron.coroutine, "__wrapped__")
        assert cron.name == f"cron:{cron.coroutine.__name__}"
    for function in settings.functions:
        assert hasattr(func(function).coroutine, "__wrapped__")


def test_disabling_the_reaper_removes_both_reaper_crons(load_worker_app) -> None:
    settings = load_worker_app(WORKER_REAP_ENABLED=False).create_worker_settings()

    assert [name for name, _, _ in _crons(settings)] == [
        "gc_expired_transfers",
        "gc_idempotency_keys",
        "gc_artifact_cache",
        "gc_trace_payloads",
    ]


def test_a_positive_audit_retention_adds_the_audit_gc_at_offset_20(load_worker_app) -> None:
    settings = load_worker_app(AUDIT_RETENTION_DAYS=30).create_worker_settings()

    assert ("gc_audit_log", [20], False) in _crons(settings)


def test_a_positive_job_history_retention_adds_the_job_history_gc_at_offset_14(
    load_worker_app,
) -> None:
    settings = load_worker_app(JOB_HISTORY_RETENTION_DAYS=30).create_worker_settings()

    assert ("gc_job_history", [14], False) in _crons(settings)


def test_a_zero_trace_retention_removes_the_trace_gc(load_worker_app) -> None:
    settings = load_worker_app(WORKER_TRACE_RETENTION_DAYS=0).create_worker_settings()

    assert "gc_trace_payloads" not in [name for name, _, _ in _crons(settings)]


@pytest.mark.parametrize(
    ("interval", "expected"),
    [(1, list(range(60))), (30, [2, 32]), (0, list(range(60)))],
)
def test_the_reaper_cadence_follows_its_interval_with_a_floor_of_one_minute(
    load_worker_app, interval, expected
) -> None:
    settings = load_worker_app(WORKER_REAP_INTERVAL_MINUTES=interval).create_worker_settings()

    assert _crons(settings)[0] == ("reap_stuck_jobs", expected, True)
