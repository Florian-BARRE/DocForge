# ====== Code Summary ======
# QueryHydeNode — the real, selectable HyDE (Hypothetical Document Embeddings) query method. It sits
# between normalize and encode (normalize → hyde → encode): it asks the provider for a short
# hypothetical passage that would answer the query, then APPENDS it to the spec's text so the encode
# node embeds the richer text (a hypothetical answer sits closer to real answer passages than a bare
# question does). Every other spec field is copied through. It inherits the bounded, degrading call
# + usage capture from BaseQueryLlmNode; any provider failure OR an empty answer yields the ORIGINAL
# query unchanged.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import QuerySpec

# ====== Local Project Imports ======
from ..base import BaseQueryLlmNode
from .config import QueryHydeConfig
from .io import QueryHydeConsumes, QueryHydeProduces

# The instruction — a short factual passage, returned as-is so it can be appended to the query text.
_SYSTEM_PROMPT = (
    "Write a short, factual hypothetical passage (2-4 sentences) that would directly answer the "
    "user's query, as if excerpted from an ideal source document. Return ONLY the passage text — "
    "no preamble, no caveats, no explanation."
)


@NodeRegistry.register("query")
class QueryHydeNode(BaseQueryLlmNode):
    """Generate a hypothetical answer passage and fold it into the query text (HyDE)."""

    KIND = "hyde"
    NAME = "HyDE"
    SUMMARY = "Generate a hypothetical answer and fold it into the query text (HyDE)."
    HOW_IT_WORKS = (
        "Asks a provider-hosted chat model for a short hypothetical passage that would answer the "
        "query, then appends it to the spec's text so encode embeds the richer text (a hypothetical "
        "answer embeds closer to real answer passages than a bare question). Every other field is "
        "copied through. The call is bounded by a wall-clock cap well under the search run cap; on "
        "any provider failure or an empty answer the ORIGINAL query is used unchanged."
    )
    Config = QueryHydeConfig
    Consumes = QueryHydeConsumes
    Produces = QueryHydeProduces

    def _prompt(self, spec: QuerySpec) -> list[tuple[str, str]]:
        """Ask the model for a hypothetical answer passage to the query."""
        return [("system", _SYSTEM_PROMPT), ("user", spec.text)]

    def _fold(self, spec: QuerySpec, answer: str) -> QuerySpec:
        """Append the passage to the query text; an empty answer keeps the original."""
        passage = answer.strip()
        if not passage:
            return spec
        return spec.model_copy(update={"text": f"{spec.text}\n\n{passage}"})


__all__ = ["QueryHydeNode"]
