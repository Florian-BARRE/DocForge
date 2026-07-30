# ====== Code Summary ======
# The hits node — the LAST node of every search pipeline: it packages the ranked hits into the
# SearchResult, the search output contract (the analog of ingestion's bundle node → RunBundle). Pure
# assembly: no model, no store. The original query text comes from the run input (the caller's ask,
# not the normalised form); a small debug bag carries the hit count. Wiring this node last is what
# makes a graph a SEARCH pipeline — the runner refuses a run whose final output is not a SearchResult.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import RankedHits, RawQuery, SearchResult


class DeliverHitsConfig(NodeConfig):
    """No knob — the hits node is a pure assembly of the run's ranked output."""


class DeliverHitsConsumes(NodeInput):
    """Input: the ranked hits + the caller's original query (from the run input)."""

    ranked: RankedHits = Field(description="The ranked hits to deliver.")
    query: RawQuery = Field(description="The caller's original query (its text labels the result).")


class DeliverHitsProduces(NodeOutput):
    """Output: the search pipeline's terminal contract."""

    result: SearchResult = Field(description="The terminal SearchResult the runner returns.")


@NodeRegistry.register("deliver")
class DeliverHitsNode(ActionNode):
    """Close the search pipeline: package the ranked hits into the SearchResult contract."""

    KIND = "hits"
    NAME = "Search result"
    SUMMARY = "Assemble the ranked hits into the search pipeline's output contract."
    HOW_IT_WORKS = (
        "Packages the ranked hits + the caller's original query text into ONE SearchResult, with a "
        "small debug bag (hit count). Pure assembly — wiring this node last is what makes the graph "
        "a search pipeline the runner can return."
    )
    Config = DeliverHitsConfig
    Consumes = DeliverHitsConsumes
    Produces = DeliverHitsProduces
    UNIQUE_IN_GRAPH = True

    async def run(self, data: DeliverHitsConsumes) -> DeliverHitsProduces:
        """
        Assemble the terminal SearchResult.

        Args:
            data (DeliverHitsConsumes): The ranked hits + the caller's original query.

        Returns:
            DeliverHitsProduces: The SearchResult the runner returns.
        """
        # 1. Pure assembly — the hits pass through untouched; the query labels the result.
        hits = data.ranked.hits
        return DeliverHitsProduces(
            result=SearchResult(
                query=data.query.text,
                hits=hits,
                debug={"hit_count": len(hits)},
            )
        )


__all__ = ["DeliverHitsNode", "DeliverHitsConfig", "DeliverHitsConsumes", "DeliverHitsProduces"]
