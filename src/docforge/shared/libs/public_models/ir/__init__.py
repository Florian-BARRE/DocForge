# ---------------------- Classification enums ---------------------- #
from .enums import BlockType, FigureKind

# ---------------------- Figure taxonomy routing (single source) ---------------------- #
from .figure_routing import FIGURE_ROUTING, FigureRouting, figure_prompt_lines

# ---------------------- Block components ---------------------- #
from .provenance import Provenance
from .table import TableData
from .figure import FigureEnrichment
from .block import Block

# ---------------------- Document (the pivot) ---------------------- #
from .document import DocumentIR

# ---------------------- Document-structure helpers ---------------------- #
from .structure import TOC_TITLES, first_heading, is_toc_title

# ------------------- Public API ------------------- #
__all__ = [
    "BlockType",
    "FigureKind",
    "FigureRouting",
    "FIGURE_ROUTING",
    "figure_prompt_lines",
    "Provenance",
    "TableData",
    "FigureEnrichment",
    "Block",
    "DocumentIR",
    "TOC_TITLES",
    "is_toc_title",
    "first_heading",
]
