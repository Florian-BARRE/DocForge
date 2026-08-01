# ====== Code Summary ======
# QueryRewriteConfig — the rewrite method's node config. It carries no knobs of its own: a query
# rewrite is fully defined by its provider endpoint + generation settings, all inherited from
# BaseQueryLlmConfig. A named subclass gives the UI its own config schema (extra="forbid": a typo in
# the stored search blob fails the build loudly).

# ====== Local Project Imports ======
from ..base import BaseQueryLlmConfig


class QueryRewriteConfig(BaseQueryLlmConfig):
    """Provider endpoint + generation knobs for the LLM query-rewrite method."""


__all__ = ["QueryRewriteConfig"]
