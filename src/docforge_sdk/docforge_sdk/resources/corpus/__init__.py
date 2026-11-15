# ====== Code Summary ======
# The document-grid query + bulk delete/enable/reingest resource package. AsyncCorpus and SyncCorpus
# are re-exported from their sub-modules, so ``docforge_sdk.resources.corpus`` stays the import path
# it always was; the spec builders live once in ``specs``, and ``sync_corpus`` is generated from
# ``async_corpus`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_corpus import AsyncCorpus
from .sync_corpus import SyncCorpus

# ------------------- Public API ------------------- #
__all__ = ["AsyncCorpus", "SyncCorpus"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.corpus``.
pin_module_path(__name__, globals(), __all__)
