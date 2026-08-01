# ====== Code Summary ======
# QueryRewriteNode — the real, selectable LLM query-rewrite method. It sits between normalize and
# encode (normalize → rewrite → encode): it asks the provider to rewrite/expand the query text into
# a stronger retrieval formulation and REPLACES only the spec's text with it (filters, top_k,
# candidate_k, search_targets and flags are all copied through). It inherits the bounded, degrading
# call + usage capture from BaseQueryLlmNode; it contributes only its prompt and its fold. Degrade
# discipline: any provider failure OR an empty answer yields the ORIGINAL query unchanged.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import QuerySpec

# ====== Local Project Imports ======
from ..base import BaseQueryLlmNode
from .config import QueryRewriteConfig
from .io import QueryRewriteConsumes, QueryRewriteProduces

# The instruction — ask for ONLY the rewritten query text so the answer can be used as-is.
_SYSTEM_PROMPT = (
    "You rewrite a user's search query into a single, stronger query for document retrieval. "
    "Expand abbreviations, make the intent explicit and add the most salient synonyms, keeping it "
    "concise. Return ONLY the rewritten query text — no preamble, no quotes, no explanation."
)


@NodeRegistry.register("query")
class QueryRewriteNode(BaseQueryLlmNode):
    """Rewrite the query text into a stronger retrieval formulation via an LLM."""

    KIND = "rewrite"
    NAME = "Rewrite query"
    SUMMARY = "LLM rewrite of the query text into a stronger retrieval formulation."
    HOW_IT_WORKS = (
        "Sends the normalised query text to a provider-hosted chat model asking for a single "
        "rewritten query, then replaces the spec's text with it (every other field — filters, "
        "top_k, candidate_k, search_targets, flags — is copied through). The call is bounded by a "
        "wall-clock cap well under the search run cap; on any provider failure or an empty answer "
        "the ORIGINAL query is used unchanged, so an enabled rewrite never breaks a search."
    )
    Config = QueryRewriteConfig
    Consumes = QueryRewriteConsumes
    Produces = QueryRewriteProduces

    def _prompt(self, spec: QuerySpec) -> list[tuple[str, str]]:
        """Ask the model to rewrite the query text (system instruction + the query as the turn)."""
        return [("system", _SYSTEM_PROMPT), ("user", spec.text)]

    def _fold(self, spec: QuerySpec, answer: str) -> QuerySpec:
        """Replace only the spec's text with the rewrite; an empty answer keeps the original."""
        rewritten = answer.strip()
        if not rewritten:
            return spec
        return spec.model_copy(update={"text": rewritten})


__all__ = ["QueryRewriteNode"]
