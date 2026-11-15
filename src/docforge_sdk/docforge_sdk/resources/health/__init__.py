# ====== Code Summary ======
# The liveness probe resource package. AsyncHealth and SyncHealth are re-exported from their
# sub-modules, so ``docforge_sdk.resources.health`` stays the import path it always was; the spec
# builders live once in ``specs``, and ``sync_health`` is generated from ``async_health``
# (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_health import AsyncHealth
from .sync_health import SyncHealth

# ------------------- Public API ------------------- #
__all__ = ["AsyncHealth", "SyncHealth"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.health``.
pin_module_path(__name__, globals(), __all__)
