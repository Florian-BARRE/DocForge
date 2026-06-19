# ====== Code Summary ======
# Thin re-export shim — preserves the public import path ``libs.engine.engine``
# for all existing callers (entrypoint.py, worker.py, tasks.py, backend/context.py).
# The actual implementation lives in libs.engine.orchestrator (sub-package).

# ====== Local Project Imports ======
from .orchestrator.core import StageEngine
from .orchestrator.result import EngineResult

# ------------------- Public API ------------------- #
__all__ = [
    "EngineResult",
    "StageEngine",
]
