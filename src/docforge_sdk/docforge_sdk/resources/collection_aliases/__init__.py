# ====== Code Summary ======
# The collection aliases resource package. AsyncCollectionAliases and SyncCollectionAliases are
# re-exported from their sub-modules, so ``docforge_sdk.resources.collection_aliases`` stays the
# import path it always was; the spec builders live once in ``specs``, and
# ``sync_collection_aliases`` is generated from ``async_collection_aliases``
# (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_collection_aliases import AsyncCollectionAliases
from .sync_collection_aliases import SyncCollectionAliases

# ------------------- Public API ------------------- #
__all__ = ["AsyncCollectionAliases", "SyncCollectionAliases"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.collection_aliases``.
pin_module_path(__name__, globals(), __all__)
