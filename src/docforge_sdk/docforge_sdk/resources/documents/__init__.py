# ====== Code Summary ======
# The document admission and searchability control resource package. AsyncDocuments and
# SyncDocuments are re-exported from their sub-modules, so ``docforge_sdk.resources.documents``
# stays the import path it always was; the spec builders live once in ``specs``, and
# ``sync_documents`` is generated from ``async_documents`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_documents import AsyncDocuments
from .sync_documents import SyncDocuments

# ------------------- Public API ------------------- #
__all__ = ["AsyncDocuments", "SyncDocuments"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.documents``.
pin_module_path(__name__, globals(), __all__)
