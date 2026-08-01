# ====== Code Summary ======
# The rewrite node's typed faces. It CONSUMES a normalised QuerySpec and PRODUCES a QuerySpec whose
# text is the rewritten query (all other fields copied through) — the SAME artefact the normalize
# node emits, so encode/retrieve/hydrate consume it unchanged. Both faces are the shared
# query-LLM faces; named subclasses give the node its own I/O identity.

# ====== Local Project Imports ======
from ..base import QueryLlmConsumes, QueryLlmProduces


class QueryRewriteConsumes(QueryLlmConsumes):
    """Input: the normalised query to rewrite."""


class QueryRewriteProduces(QueryLlmProduces):
    """Output: the query with its text rewritten into a stronger retrieval formulation."""


__all__ = ["QueryRewriteConsumes", "QueryRewriteProduces"]
