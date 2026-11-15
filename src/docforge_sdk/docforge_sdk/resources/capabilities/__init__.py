# ====== Code Summary ======
# The deployment discovery resource package. AsyncCapabilities and SyncCapabilities are re-exported
# from their sub-modules, so ``docforge_sdk.resources.capabilities`` stays the import path it always
# was; the spec builders live once in ``specs``, and ``sync_capabilities`` is generated from
# ``async_capabilities`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_capabilities import AsyncCapabilities
from .sync_capabilities import SyncCapabilities

# ------------------- Public API ------------------- #
__all__ = ["AsyncCapabilities", "SyncCapabilities"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.capabilities``.
pin_module_path(__name__, globals(), __all__)
