# ====== Code Summary ======
# IngestStageIngestStepBase — the family base for every step of the ingest stage. It pins KIND=STEP
# so concrete steps only declare their SPEC + IO + Context + run logic. A thin abstract node (it is
# never run directly): it opts out of the SPEC check with abstract=True.

# ====== Internal Project Imports ======
from common_libs2.pipelines import LeafNode, NodeKind

# ====== Local Project Imports ======
from .errors import IngestStageIngestStepError


class IngestStageIngestStepBase(LeafNode, abstract=True):
    """Abstract base for the ingest stage's steps — fixes the KIND and the default step error."""

    KIND = NodeKind.STEP
    Error = IngestStageIngestStepError


__all__ = ["IngestStageIngestStepBase"]
