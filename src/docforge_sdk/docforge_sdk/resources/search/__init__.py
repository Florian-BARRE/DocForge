# ====== Code Summary ======
# The hybrid search resource package. AsyncSearch and SyncSearch are re-exported from their
# sub-modules, so ``docforge_sdk.resources.search`` stays the import path it always was; the spec
# builders live once in ``specs``, and ``sync_search`` is generated from ``async_search``
# (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_search import AsyncSearch
from .sync_search import SyncSearch

# ------------------- Public API ------------------- #
__all__ = ["AsyncSearch", "SyncSearch"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.search``.
pin_module_path(__name__, globals(), __all__)
