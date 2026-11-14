# ====== Code Summary ======
# The document explorer (catalogue, detail, pages, IR, chunks, chunk toggles) resource package.
# AsyncExplorer and SyncExplorer are re-exported from their sub-modules, so
# ``docforge_sdk.resources.explorer`` stays the import path it always was; the spec builders live once
# in ``specs``.

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_explorer import AsyncExplorer
from .sync_explorer import SyncExplorer

# ------------------- Public API ------------------- #
__all__ = ["AsyncExplorer", "SyncExplorer"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.explorer``.
pin_module_path(__name__, globals(), __all__)
