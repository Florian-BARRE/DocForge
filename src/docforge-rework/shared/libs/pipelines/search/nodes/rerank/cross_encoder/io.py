# ====== Code Summary ======
# The cross-encoder rerank node's typed faces. It CONSUMES the fused candidate pool + the query spec
# (it judges each passage against the query text). It PRODUCES a re-scored CandidateSet — the SAME
# artefact the retrieve node emits, so the downstream hydrate node consumes it unchanged (the graph
# stays retrieve → rerank → hydrate). The Produces face subclasses ScoredOutput (the top-1 rerank
# score), so a future ScoreBelow edge can escalate to a stronger reranker without any face change.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, ScoredOutput
from shared_libs.public_models.search import CandidateSet, QuerySpec


class RerankCrossEncoderConsumes(NodeInput):
    """Input: the fused candidate pool to re-score + the query whose text the model judges."""

    candidates: CandidateSet = Field(description="The fused candidate pool to re-score.")
    spec: QuerySpec = Field(
        description="The normalised query — its text is judged against each candidate passage."
    )


class RerankCrossEncoderProduces(ScoredOutput):
    """Output: the re-scored pool (as a plain CandidateSet) + the top-1 score a ScoreBelow gates on."""

    candidates: CandidateSet = Field(
        description="The re-scored candidate pool (cross-encoder scores in [0, 1]), best-first."
    )


__all__ = ["RerankCrossEncoderConsumes", "RerankCrossEncoderProduces"]
