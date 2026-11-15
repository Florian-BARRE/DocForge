# ====== Code Summary ======
# The root-only audit-trail reads resource package. AsyncAudit and SyncAudit are re-exported from
# their sub-modules, so ``docforge_sdk.resources.audit`` stays the import path it always was; the
# spec builders live once in ``specs``, and ``sync_audit`` is generated from ``async_audit``
# (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_audit import AsyncAudit
from .sync_audit import SyncAudit

# ------------------- Public API ------------------- #
__all__ = ["AsyncAudit", "SyncAudit"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.audit``.
pin_module_path(__name__, globals(), __all__)
