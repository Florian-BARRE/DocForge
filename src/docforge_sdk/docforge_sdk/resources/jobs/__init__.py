# ====== Code Summary ======
# The jobs (the live ingestion status the UI polls) resource package.
# AsyncJobs and SyncJobs are re-exported from their sub-modules, so
# ``docforge_sdk.resources.jobs`` stays the import path it always was; the spec builders live once
# in ``specs``.

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_jobs import AsyncJobs
from .sync_jobs import SyncJobs

# ------------------- Public API ------------------- #
__all__ = ["AsyncJobs", "SyncJobs"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.jobs``.
pin_module_path(__name__, globals(), __all__)
