# Import all three config modules to trigger their @register("split_method") decorators.
# These side-effect imports populate the registry so build_union(get_configs("split_method"))
# can assemble the SplitMethodConfig discriminated union.
from .semantic import SemanticConfig
from .sentence_window import SentenceWindowConfig
from .token_budget import TokenBudgetConfig

# ─────────────────── Public API ─────────────────────────────────────── #
__all__ = [
    "SemanticConfig",
    "SentenceWindowConfig",
    "TokenBudgetConfig",
]
