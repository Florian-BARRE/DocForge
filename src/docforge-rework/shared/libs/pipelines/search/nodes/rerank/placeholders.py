# ====== Code Summary ======
# Future rerank methods (SELECTABLE=False): ColBERT MAX_SIM, cross-encoder, and LLM listwise. Their
# shared OUTPUT face subclasses ScoredOutput, so describe().scored is True and a ScoreBelow
# escalation edge is legal on any of them (the escalation chain the research doc plans for P2).
# Registered with typed described faces for discoverability; bodies raise until then.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, ScoredOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, EncodedQuery, QuerySpec, ScoredCandidates

# ====== Local Project Imports ======
from ..placeholder import PlaceholderNode


class _RerankPlaceholderConfig(NodeConfig):
    """Knob-less config shared by the rerank placeholders."""


class _RerankVectorConsumes(NodeInput):
    """Consumes the candidate pool + the query vectors (a vector re-score)."""

    candidates: CandidateSet = Field(description="The candidate pool to re-score.")
    encoded: EncodedQuery = Field(description="The query vectors driving the re-score (e.g. ColBERT).")


class _RerankTextConsumes(NodeInput):
    """Consumes the candidate pool + the query text (a model judge)."""

    candidates: CandidateSet = Field(description="The candidate pool to re-score.")
    spec: QuerySpec = Field(description="The query whose text the model judges relevance against.")


class _ScoredRerankProduces(ScoredOutput):
    """Produces a re-scored pool + an aggregate score a ScoreBelow edge can gate on."""

    reranked: ScoredCandidates = Field(description="The re-scored candidate pool, best-first.")


@NodeRegistry.register("rerank")
class RerankColbertNode(PlaceholderNode):
    """ColBERT late-interaction MAX_SIM re-score over the pool (future)."""

    KIND = "colbert"
    NAME = "ColBERT rerank"
    SUMMARY = "Late-interaction MAX_SIM re-score of the pool with the query's ColBERT vectors."
    Config = _RerankPlaceholderConfig
    Consumes = _RerankVectorConsumes
    Produces = _ScoredRerankProduces


@NodeRegistry.register("rerank")
class RerankCrossEncoderNode(PlaceholderNode):
    """Cross-encoder re-score via a reranker endpoint (future)."""

    KIND = "cross_encoder"
    NAME = "Cross-encoder rerank"
    SUMMARY = "Re-score each candidate with a cross-encoder reranker (query, passage) pair."
    Config = _RerankPlaceholderConfig
    Consumes = _RerankTextConsumes
    Produces = _ScoredRerankProduces


@NodeRegistry.register("rerank")
class RerankLlmNode(PlaceholderNode):
    """LLM listwise re-ranking judge (future — the escalation target)."""

    KIND = "llm"
    NAME = "LLM rerank"
    SUMMARY = "LLM listwise judge that re-orders the candidate pool by relevance."
    Config = _RerankPlaceholderConfig
    Consumes = _RerankTextConsumes
    Produces = _ScoredRerankProduces


__all__ = ["RerankColbertNode", "RerankCrossEncoderNode", "RerankLlmNode"]
