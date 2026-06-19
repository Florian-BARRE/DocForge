# ─────── Trigger @register decorators for split-method configs ─────── #
# This import causes config/__init__.py to run, which imports all three
# config modules and fires their @register("split_method") decorators.
from . import config as _config_bootstrap  # noqa: F401

# ------------------- Stage ------------------- #
from .core import S4ChunkStage

# ------------------- Result ------------------- #
from .models import S4Result

# ─────────────────── Splitter implementations (re-exported) ─────────── #
from .strategies import (
    SectionSplitter,
    SemanticSplitter,
    SentenceWindowSplitter,
    SplitPiece,
    TokenBudgetSplitter,
)

# ─────────────────── Helpers (re-exported) ───────────────────────────── #
from .helpers import ChunkingHelpers, CrossReferenceLinker

# ─────────────────── Configs (re-exported) ───────────────────────────── #
from .config import SemanticConfig, SentenceWindowConfig, TokenBudgetConfig

# ------------------- Public API ------------------- #
__all__ = [
    "S4ChunkStage",
    "S4Result",
    # Splitters
    "SplitPiece",
    "SectionSplitter",
    "SemanticSplitter",
    "SentenceWindowSplitter",
    "TokenBudgetSplitter",
    # Helpers
    "ChunkingHelpers",
    "CrossReferenceLinker",
    # Configs
    "SemanticConfig",
    "SentenceWindowConfig",
    "TokenBudgetConfig",
]
