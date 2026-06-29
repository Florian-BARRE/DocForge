# ====== Code Summary ======
# IngestStageEnrichStepBase - the family base for every step of the enrich stage. It pins KIND=STEP
# so concrete steps only declare their SPEC + IO + Context + run logic. A thin abstract node (it is
# never run directly): it opts out of the SPEC check with abstract=True.

# ====== Internal Project Imports ======
from common_libs.pipelines import LeafNode, NodeKind

# ====== Local Project Imports ======
from .errors import IngestStageEnrichStepError


class IngestStageEnrichStepBase(LeafNode, abstract=True):
    """Abstract base for the enrich stage's steps - fixes the KIND and the default step error."""

    KIND = NodeKind.STEP
    Error = IngestStageEnrichStepError


__all__ = ["IngestStageEnrichStepBase"]
