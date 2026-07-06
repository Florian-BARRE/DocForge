# ---------------------- Classification enums ---------------------- #
from .enums import BlockType, FigureKind

# ---------------------- Block components ---------------------- #
from .provenance import Provenance
from .table import TableData
from .figure import FigureEnrichment
from .block import Block

# ---------------------- Document (the pivot) ---------------------- #
from .document import DocumentIR

# ------------------- Public API ------------------- #
__all__ = [
    "BlockType",
    "FigureKind",
    "Provenance",
    "TableData",
    "FigureEnrichment",
    "Block",
    "DocumentIR",
]
