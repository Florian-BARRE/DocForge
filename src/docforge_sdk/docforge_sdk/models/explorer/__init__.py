# ====== Code Summary ======
# Response/request models for the document explorer resource, mirrored field-for-field from the DocForge
# backend router models. The classes live in sub-modules by concern (documents, chunks, chunk toggles)
# and are re-exported here, so ``docforge_sdk.models.explorer`` stays the import path it always was.

# ====== Local Project Imports ======
from .._reexport import pin_module_path
from .._shared import DocumentStatus as DocumentStatus
from .._shared import FieldOrigin as FieldOrigin
from .._shared import SourceKind as SourceKind
from .chunk_toggles import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkEnabledPatch,
    ChunkEnabledResult,
)
from .chunks import ChunkContext, ChunkInfo, ChunkPage, ContextChunk
from .documents import (
    DocumentDetail,
    DocumentListItem,
    DocumentOutline,
    MetadataValue,
    OutlineHeading,
    PageInfo,
)

# ------------------- Public API ------------------- #
__all__ = [
    "MetadataValue",
    "DocumentListItem",
    "DocumentDetail",
    "PageInfo",
    "ChunkInfo",
    "ChunkPage",
    "OutlineHeading",
    "DocumentOutline",
    "ContextChunk",
    "ChunkContext",
    "ChunkEnabledPatch",
    "BulkChunkEnabledPatch",
    "ChunkEnabledResult",
    "BulkChunkEnabledResponse",
]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.models.explorer``.
pin_module_path(__name__, globals(), __all__)
