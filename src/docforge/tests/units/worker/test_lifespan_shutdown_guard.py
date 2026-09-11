# ====== Code Summary ======
# Repro/guard: arq 0.28 calls `log_redis_info()` in its own `main()` BEFORE `on_startup` — an
# ACL-hardened Redis that denies `INFO` crashes the worker there, so `worker.backend.lifespan.startup`
# NEVER runs, yet arq still calls `on_shutdown`. `shutdown()` must therefore tolerate a CONTEXT that
# has no `logger`/`heartbeat`/`database` at all, or an unguarded `CONTEXT.logger` access raises
# AttributeError and MASKS the real startup error. Run in an ISOLATED subprocess: `worker/backend`
# and `app/backend` both define a top-level `backend`/`config` package, so importing the worker's
# lifespan into the shared pytest session would collide with the app tests' own `backend`/`config`
# (see tests/units/worker/conftest.py header for the same collision handled a different way).

# ====== Standard Library Imports ======
import os
import subprocess
import sys
from pathlib import Path

# ====== Third-Party Library Imports ======
import pytest

# The worker's own root (contains `config/` + `backend/`), independent of the app's roots the
# session conftest already wired — mirrors the worker entrypoint contract (config imported first).
_DOCFORGE_ROOT = Path(__file__).resolve().parents[3]
_WORKER_ROOT = _DOCFORGE_ROOT / "worker"
_SUCCESS_SENTINEL = "SHUTDOWN_SURVIVED_NEVER_STARTED_CONTEXT"

# Minimal env for the worker's RUNTIME_CONFIG import: every var without a default in
# worker/config/runtime_config.py, plus the 5 mandatory LOGGING_* vars. Values are throwaway —
# nothing here ever opens a real connection (shutdown() short-circuits before any I/O).
_WORKER_ENV = {
    "REDIS_URL": "redis://localhost:1/0",
    "POSTGRES_DSN": "postgresql+asyncpg://u:p@localhost/db",
    "QDRANT_URL": "http://localhost:1",
    "S3_ENDPOINT_URL": "http://localhost:1",
    "S3_ACCESS_KEY": "x",
    "S3_SECRET_KEY": "x",
    "S3_BUCKET": "x",
    "LOGGING_CONSOLE_LEVEL": "INFO",
    "LOGGING_FILE_LEVEL": "DEBUG",
    "LOGGING_ENABLE_CONSOLE": "false",
    "LOGGING_ENABLE_FILE": "false",
    "LOGGING_LPP_FORMAT": "ShortFormat",
}

_SUBPROCESS_SCRIPT = f"""
import asyncio
import sys

sys.path.insert(0, {str(_WORKER_ROOT)!r})

# Worker config MUST import first — it registers the `shared_libs` alias + backend/libs on sys.path.
from config import RUNTIME_CONFIG  # noqa: F401
from backend import lifespan
import types

# A worker that crashed before on_startup ran: CONTEXT carries none of logger/heartbeat/database.
lifespan.CONTEXT = types.SimpleNamespace()

asyncio.run(lifespan.shutdown({{}}))
print({_SUCCESS_SENTINEL!r})
"""


def test_shutdown_survives_never_started_context() -> None:
    """`shutdown()` must not raise when `startup()` never ran (no logger/heartbeat/database)."""
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        cwd=str(_DOCFORGE_ROOT),
        env={**os.environ, **_WORKER_ENV},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"shutdown() raised in a never-started worker — the exact masking bug this guards.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert _SUCCESS_SENTINEL in result.stdout


@pytest.mark.parametrize("missing_attr", ["logger", "heartbeat", "database"])
def test_shutdown_guard_targets_the_documented_attributes(missing_attr: str) -> None:
    """Sanity: the three attributes this guard cares about are exactly what startup() sets first."""
    lifespan_source = (_WORKER_ROOT / "backend" / "lifespan.py").read_text()
    assert f'hasattr(CONTEXT, "{missing_attr}")' in lifespan_source or missing_attr == "logger"
    if missing_attr == "logger":
        assert 'getattr(CONTEXT, "logger", None)' in lifespan_source
