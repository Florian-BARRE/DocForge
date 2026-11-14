# ====== Code Summary ======
# Request/response models for the search resource, mirrored field-for-field from the DocForge backend
# router models. The classes live in sub-modules (requests, responses) and are re-exported here, so
# ``docforge_sdk.models.search`` stays the import path it always was.

# ====== Local Project Imports ======
from .._reexport import pin_module_path
from .requests import ChunkBrowseRequest, SearchRequest, SearchTarget
from .responses import (
    BlockLocation,
    ChunkBrowseResponse,
    SearchCost,
    SearchHealthSummary,
    SearchHint,
    SearchHit,
    SearchResponse,
)

# ------------------- Public API ------------------- #
__all__ = [
    "SearchTarget",
    "SearchRequest",
    "BlockLocation",
    "SearchHit",
    "SearchCost",
    "SearchHint",
    "SearchResponse",
    "ChunkBrowseRequest",
    "ChunkBrowseResponse",
    "SearchHealthSummary",
]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.models.search``.
pin_module_path(__name__, globals(), __all__)
