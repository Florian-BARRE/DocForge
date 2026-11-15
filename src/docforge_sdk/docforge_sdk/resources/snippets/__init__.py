# ====== Code Summary ======
# The granular collection-config snippet export/apply resource package. AsyncSnippets and
# SyncSnippets are re-exported from their sub-modules, so ``docforge_sdk.resources.snippets`` stays
# the import path it always was; the spec builders live once in ``specs``, and ``sync_snippets`` is
# generated from ``async_snippets`` (scripts/generate_sync.py).

# ====== Local Project Imports ======
from ...models._reexport import pin_module_path
from .async_snippets import AsyncSnippets
from .sync_snippets import SyncSnippets

# ------------------- Public API ------------------- #
__all__ = ["AsyncSnippets", "SyncSnippets"]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.resources.snippets``.
pin_module_path(__name__, globals(), __all__)
