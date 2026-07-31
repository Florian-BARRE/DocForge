# ====== Code Summary ======
# Future rerank method (SELECTABLE=False): LLM listwise. Its OUTPUT face subclasses ScoredOutput, so
# describe().scored is True and a ScoreBelow escalation edge is legal on it (the escalation chain the
# research doc plans for P2). Registered with a typed described face for discoverability; the body
# raises until then. The cross-encoder method is no longer a placeholder — it is the real, selectable
# node in the cross_encoder/ subpackage.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, ScoredOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, QuerySpec, ScoredCandidates

# ====== Local Project Imports ======
from ..placeholder import PlaceholderNode


class _RerankPlaceholderConfig(NodeConfig):
    """Knob-less config shared by the rerank placeholders."""


class _RerankTextConsumes(NodeInput):
    """Consumes the candidate pool + the query text (a model judge)."""

    candidates: CandidateSet = Field(description="The candidate pool to re-score.")
    spec: QuerySpec = Field(description="The query whose text the model judges relevance against.")


class _ScoredRerankProduces(ScoredOutput):
    """Produces a re-scored pool + an aggregate score a ScoreBelow edge can gate on."""

    reranked: ScoredCandidates = Field(description="The re-scored candidate pool, best-first.")


@NodeRegistry.register("rerank")
class RerankLlmNode(PlaceholderNode):
    """LLM listwise re-ranking judge (future — the escalation target)."""

    KIND = "llm"
    NAME = "LLM rerank"
    SUMMARY = "LLM listwise judge that re-orders the candidate pool by relevance."
    Config = _RerankPlaceholderConfig
    Consumes = _RerankTextConsumes
    Produces = _ScoredRerankProduces


__all__ = ["RerankLlmNode"]
