# Import all three config modules to trigger their @register("split_method") decorators.
# These side-effect imports populate the registry so build_union(get_configs("split_method"))
# can assemble the SplitMethodConfig discriminated union.
#
# Import order IS load-bearing: it drives the @register("split_method") firing order, which the
# registry / describe surface exposes to the UI. Keep token_budget -> semantic -> sentence_window
# to match the SPLIT_METHOD_PARAMS catalog (asserted by the test_registry_schema drift guards).
# The libs-reorg refactor alphabetised these, which silently flipped the registered order.
from .token_budget import TokenBudgetConfig  # noqa: I001
from .semantic import SemanticConfig
from .sentence_window import SentenceWindowConfig

# ─────────────────── Public API ─────────────────────────────────────── #
__all__ = [
    "SemanticConfig",
    "SentenceWindowConfig",
    "TokenBudgetConfig",
]
