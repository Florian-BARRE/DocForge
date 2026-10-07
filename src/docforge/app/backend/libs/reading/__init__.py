# ---------------------- Read service (outline + chunk context) ---------------------- #
from .service import DocumentReader

# ---------------------- Pure building blocks ---------------------- #
from .chunk_enablement import ChunkEnablement
from .chunk_window import ChunkWindow
from .ir_page_filter import IRPageFilter
from .outline_builder import OutlineBuilder
from .page_range import PageRangeError, PageRangeParser

# ---------------------- API response contract ---------------------- #
from .models import ChunkContext, ContextChunk, DocumentOutline, OutlineHeading

# ------------------- Public API ------------------- #
__all__ = [
    "DocumentReader",
    "ChunkEnablement",
    "ChunkWindow",
    "IRPageFilter",
    "OutlineBuilder",
    "PageRangeError",
    "PageRangeParser",
    "ChunkContext",
    "ContextChunk",
    "DocumentOutline",
    "OutlineHeading",
]
