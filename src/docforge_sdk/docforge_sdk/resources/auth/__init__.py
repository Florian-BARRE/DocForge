# ====== Code Summary ======
# The API-key management (create / list / revoke / rotate) resource package. AsyncAuth and SyncAuth
# are re-exported from their sub-modules, so ``docforge_sdk.resources.auth`` stays the import path
# it always was; the spec builders live once in ``specs``, and ``sync_auth`` is generated from
# ``async_auth`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_auth import AsyncAuth
from .sync_auth import SyncAuth

# ------------------- Public API ------------------- #
__all__ = ["AsyncAuth", "SyncAuth"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.auth``.
pin_module_path(__name__, globals(), __all__)
