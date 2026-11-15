# ====== Code Summary ======
# The collection config history resource package. AsyncConfigVersions and SyncConfigVersions are
# re-exported from their sub-modules, so ``docforge_sdk.resources.config_versions`` stays the import
# path it always was; the spec builders live once in ``specs``, and ``sync_config_versions`` is
# generated from ``async_config_versions`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_config_versions import AsyncConfigVersions
from .sync_config_versions import SyncConfigVersions

# ------------------- Public API ------------------- #
__all__ = ["AsyncConfigVersions", "SyncConfigVersions"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.config_versions``.
pin_module_path(__name__, globals(), __all__)
