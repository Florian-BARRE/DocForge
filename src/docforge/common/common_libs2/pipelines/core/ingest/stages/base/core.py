# ====== Code Summary ======
# IngestStageBase — the family base for every stage of the ingest pipeline. It pins KIND=STAGE so a
# concrete stage only declares its SPEC + IO + Context + children. Abstract (never run directly).

# ====== Internal Project Imports ======
from common_libs2.pipelines import CompositeNode, NodeKind


class IngestStageBase(CompositeNode, abstract=True):
    """Abstract base for the ingest pipeline's stages — fixes the node KIND to STAGE."""

    KIND = NodeKind.STAGE


__all__ = ["IngestStageBase"]
