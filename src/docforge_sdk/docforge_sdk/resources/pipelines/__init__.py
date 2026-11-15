# ====== Code Summary ======
# The pipeline discovery + design surface resource package. AsyncPipelines and SyncPipelines are
# re-exported from their sub-modules, so ``docforge_sdk.resources.pipelines`` stays the import path
# it always was; the spec builders live once in ``specs``, and ``sync_pipelines`` is generated from
# ``async_pipelines`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_pipelines import AsyncPipelines
from .sync_pipelines import SyncPipelines

# ------------------- Public API ------------------- #
__all__ = ["AsyncPipelines", "SyncPipelines"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.pipelines``.
pin_module_path(__name__, globals(), __all__)
