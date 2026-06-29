# ---------------------- Engine ------------------------------- #
from .engine import StructureAwareChunker

# ---------------------- Result ------------------------------- #
from .models import S4Result

# ---------------------- Split contract + methods ------------- #
from .strategies import (
    SectionSplitter,
    SemanticSplitter,
    SentenceWindowSplitter,
    SplitPiece,
    TokenBudgetSplitter,
)

# ---------------------- Cross-reference linker --------------- #
from .linker import CrossReferenceLinker

# ---------------------- Public API --------------------------- #
__all__ = [
    "StructureAwareChunker",
    "S4Result",
    "SectionSplitter",
    "SplitPiece",
    "TokenBudgetSplitter",
    "SentenceWindowSplitter",
    "SemanticSplitter",
    "CrossReferenceLinker",
]
