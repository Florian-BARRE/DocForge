# ====== Code Summary ======
# arq worker entry point for DocForge.
# Target for the arq CLI: `arq arq_worker.WorkerSettings`
# Run from WORKDIR /app/worker.

# ====== Path bootstrap (multi-root layout) ======
# This app lives in src/worker/; shared code lives in src/common/. Register both on
# sys.path BEFORE any internal import so that:
#   - src/common  resolves `config` and `common_libs.*`  (shared)
#   - src/worker  resolves `arq_worker` and `libs.*`  (worker-dedicated pipeline)
import pathlib as _pathlib
import sys as _sys

_WORKER_DIR = _pathlib.Path(__file__).resolve().parent
_COMMON_DIR = _WORKER_DIR.parent / "common"
for _p in (_COMMON_DIR, _WORKER_DIR):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

# ====== Internal Project Imports ======
# RUNTIME_CONFIG must be imported first — registers the shared common/ tree on sys.path.
from config import RUNTIME_CONFIG  # noqa: F401 — side-effect import, configures logging

# ====== Local Project Imports ======
from libs.pipeline.worker.worker import WorkerSettings  # noqa: F401 — arq CLI target

__all__ = ["WorkerSettings"]
