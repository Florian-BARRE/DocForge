# ====== Code Summary ======
# The collection export/import — trigger, poll, and streamed bundle download resource package.
# AsyncTransfers and SyncTransfers are re-exported from their sub-modules, so
# ``docforge_sdk.resources.transfers`` stays the import path it always was; the spec builders live
# once in ``specs``, and ``sync_transfers`` is generated from ``async_transfers``
# (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_transfers import AsyncTransfers
from .sync_transfers import SyncTransfers

# ------------------- Public API ------------------- #
__all__ = ["AsyncTransfers", "SyncTransfers"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.transfers``.
pin_module_path(__name__, globals(), __all__)
