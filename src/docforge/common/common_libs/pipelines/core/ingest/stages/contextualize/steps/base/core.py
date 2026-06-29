# ====== Code Summary ======
# IngestStageContextualizeStepBase — the family base for every step of the contextualize stage. It
# pins KIND=STEP so concrete steps only declare their SPEC + IO + Context + run logic. A thin abstract
# node (never run directly): it opts out of the SPEC check with abstract=True.

# ====== Internal Project Imports ======
from common_libs.pipelines import LeafNode, NodeKind

# ====== Local Project Imports ======
from .errors import IngestStageContextualizeStepError


class IngestStageContextualizeStepBase(LeafNode, abstract=True):
    """Abstract base for the contextualize stage's steps — fixes the KIND and the default step error."""

    KIND = NodeKind.STEP
    Error = IngestStageContextualizeStepError


__all__ = ["IngestStageContextualizeStepBase"]
