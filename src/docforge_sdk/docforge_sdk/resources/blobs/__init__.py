# ====== Code Summary ======
# The content-addressed blob fetch resource package. AsyncBlobs and SyncBlobs are re-exported from
# their sub-modules, so ``docforge_sdk.resources.blobs`` stays the import path it always was; the
# spec builders live once in ``specs``, and ``sync_blobs`` is generated from ``async_blobs``
# (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_blobs import AsyncBlobs
from .sync_blobs import SyncBlobs

# ------------------- Public API ------------------- #
__all__ = ["AsyncBlobs", "SyncBlobs"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.blobs``.
pin_module_path(__name__, globals(), __all__)
