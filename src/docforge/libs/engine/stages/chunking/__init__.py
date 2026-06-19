# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all split method configs and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

# NOTE: split method configs live in params.py (not in local/external), so we
# import params.py directly to trigger @register("split_method") decorators.
from libs.core.contracts._registry import build_union, get_configs

from . import params as _params_module  # noqa: F401 — side-effect: triggers @register

# ------------------- Splitter implementations ------------------- #
from .base_splitter import SectionSplitter
from .cross_reference_linker import CrossReferenceLinker

# ------------------- Helpers ------------------- #
from .helpers import ChunkingHelpers

# ------------------- Split Method Configs ------------------- #
from .params import (
    SPLIT_METHOD_PARAMS,
    SemanticConfig,
    SemanticParams,
    SentenceWindowConfig,
    SentenceWindowParams,
    TokenBudgetConfig,
    TokenBudgetParams,
)
from .semantic_splitter import SemanticSplitter
from .sentence_window_splitter import SentenceWindowSplitter
from .token_budget_splitter import TokenBudgetSplitter

# ------------------- Discriminated Union ------------------- #
SplitMethodConfig = build_union(get_configs("split_method"))

# ------------------- Public API ------------------- #
__all__ = [
    "ChunkingHelpers",
    "CrossReferenceLinker",
    "SPLIT_METHOD_PARAMS",
    "SectionSplitter",
    "SemanticConfig",
    "SemanticParams",
    "SemanticSplitter",
    "SentenceWindowConfig",
    "SentenceWindowParams",
    "SentenceWindowSplitter",
    "SplitMethodConfig",
    "TokenBudgetConfig",
    "TokenBudgetParams",
    "TokenBudgetSplitter",
]
