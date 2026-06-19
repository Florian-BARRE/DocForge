# ====== Code Summary ======
# Aggregator for the intra-section split-method configs.  Each split method is a typed
# Pydantic discriminated-union member living in its own module
# (token_budget_config / semantic_config / sentence_window_config).  Importing them here
# triggers their @register("split_method") decorators (the chunking __init__ imports this
# module as a side-effect) and lets the rest of the codebase keep importing the configs,
# the legacy *Params aliases, and the SPLIT_METHOD_PARAMS catalog from one place.

from __future__ import annotations  # noqa: I001 — import order below is load-bearing

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
# NOTE: import order IS significant — it drives @register("split_method") firing order,
# which the registry/describe surface surfaces to the UI.  Keep token_budget → semantic →
# sentence_window to match the SPLIT_METHOD_PARAMS catalog order (asserted by a guard test).
from ..config.token_budget import TokenBudgetConfig
from ..config.semantic import SemanticConfig
from ..config.sentence_window import SentenceWindowConfig

# Backward-compat aliases (old name → new name)
TokenBudgetParams = TokenBudgetConfig
SemanticParams = SemanticConfig
SentenceWindowParams = SentenceWindowConfig

# Source-of-truth catalog: split method id → its config model.
# derive_stages(), registry builder, and docs all derive from this.
SPLIT_METHOD_PARAMS: dict[str, type[BaseModel]] = {
    "token_budget": TokenBudgetConfig,
    "semantic": SemanticConfig,
    "sentence_window": SentenceWindowConfig,
}


# ------------------- Public API ------------------- #
__all__ = [
    "TokenBudgetConfig",
    "SemanticConfig",
    "SentenceWindowConfig",
    "TokenBudgetParams",
    "SemanticParams",
    "SentenceWindowParams",
    "SPLIT_METHOD_PARAMS",
]
