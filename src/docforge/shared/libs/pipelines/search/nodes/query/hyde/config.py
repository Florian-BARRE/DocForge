# ====== Code Summary ======
# QueryHydeConfig — the HyDE method's node config. Like the rewrite method it carries no knobs of
# its own: a HyDE call is fully defined by its provider endpoint + generation settings, all
# inherited from BaseQueryLlmConfig. A named subclass gives the UI its own config schema
# (extra="forbid": a typo in the stored search blob fails the build loudly).

# ====== Local Project Imports ======
from ..base import BaseQueryLlmConfig


class QueryHydeConfig(BaseQueryLlmConfig):
    """Provider endpoint + generation knobs for the LLM HyDE method."""


__all__ = ["QueryHydeConfig"]
