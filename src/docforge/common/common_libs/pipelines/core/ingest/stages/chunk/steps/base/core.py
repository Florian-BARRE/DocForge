# ====== Code Summary ======
# IngestStageChunkStepBase — the family base for every step of the chunk stage. It pins KIND=STEP so
# concrete steps only declare their SPEC + IO + Context + run logic. A thin abstract node (never run
# directly): it opts out of the SPEC check with abstract=True.

# ====== Internal Project Imports ======
from common_libs.pipelines import LeafNode, NodeKind

# ====== Local Project Imports ======
from .errors import IngestStageChunkStepError


class IngestStageChunkStepBase(LeafNode, abstract=True):
    """Abstract base for the chunk stage's steps — fixes the KIND and the default step error."""

    KIND = NodeKind.STEP
    Error = IngestStageChunkStepError


__all__ = ["IngestStageChunkStepBase"]
