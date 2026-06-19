# ====== Code Summary ======
# arq worker entry point for DocForge.
# Target for the arq CLI: `arq arq_worker.WorkerSettings`
# Run from WORKDIR /app/docforge (same as uvicorn target).

# ====== Internal Project Imports ======
# RUNTIME_CONFIG must be imported first — registers sys.path so `libs.*` imports resolve.
from config import RUNTIME_CONFIG  # noqa: F401 — side-effect import, registers sys.path

# ====== Local Project Imports ======
from libs.engine.worker import WorkerSettings  # noqa: F401 — arq CLI target

__all__ = ["WorkerSettings"]
