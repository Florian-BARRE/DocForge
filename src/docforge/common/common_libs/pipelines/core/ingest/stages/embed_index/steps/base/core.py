# ====== Code Summary ======
# IngestStageEmbedIndexStepBase — the family base for every step of the embed_index stage. It pins
# KIND=STEP so concrete steps only declare their SPEC + IO + Context + run logic. A thin abstract
# node (never run directly): it opts out of the SPEC check with abstract=True.

# ====== Internal Project Imports ======
from common_libs.pipelines import LeafNode, NodeKind

# ====== Local Project Imports ======
from .errors import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepBase(LeafNode, abstract=True):
    """Abstract base for the embed_index stage's steps — fixes the KIND and the default step error."""

    KIND = NodeKind.STEP
    Error = IngestStageEmbedIndexStepError


__all__ = ["IngestStageEmbedIndexStepBase"]
