# ====== Code Summary ======
# The collections (CRUD over a collection's full contract) resource package.
# AsyncCollections and SyncCollections are re-exported from their sub-modules, so
# ``docforge_sdk.resources.collections`` stays the import path it always was; the spec builders live once
# in ``specs``.

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_collections import AsyncCollections
from .sync_collections import SyncCollections

# ------------------- Public API ------------------- #
__all__ = ["AsyncCollections", "SyncCollections"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.collections``.
pin_module_path(__name__, globals(), __all__)
