# ====== Code Summary ======
# The HyDE node's typed faces. It CONSUMES a normalised QuerySpec and PRODUCES a QuerySpec whose
# text is enriched with a hypothetical answer passage (all other fields copied through) — the SAME
# artefact the normalize node emits, so encode/retrieve/hydrate consume it unchanged. Both faces are
# the shared query-LLM faces; named subclasses give the node its own I/O identity.

# ====== Local Project Imports ======
from ..base import QueryLlmConsumes, QueryLlmProduces


class QueryHydeConsumes(QueryLlmConsumes):
    """Input: the normalised query to enrich with a hypothetical answer."""


class QueryHydeProduces(QueryLlmProduces):
    """Output: the query with a hypothetical answer passage appended to its text."""


__all__ = ["QueryHydeConsumes", "QueryHydeProduces"]
