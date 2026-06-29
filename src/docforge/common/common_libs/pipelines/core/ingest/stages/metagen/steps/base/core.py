# ====== Code Summary ======
# IngestStageMetagenStepBase — the family base for every step of the metagen stage. It pins KIND=STEP
# so concrete steps only declare their SPEC + IO + Context + run logic. A thin abstract node (it is
# never run directly): it opts out of the SPEC check with abstract=True.

# ====== Internal Project Imports ======
from common_libs.pipelines import LeafNode, NodeKind

# ====== Local Project Imports ======
from .errors import IngestStageMetagenStepError


class IngestStageMetagenStepBase(LeafNode, abstract=True):
    """Abstract base for the metagen stage's steps — fixes the KIND and the default step error."""

    KIND = NodeKind.STEP
    Error = IngestStageMetagenStepError


__all__ = ["IngestStageMetagenStepBase"]
