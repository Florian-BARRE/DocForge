# ====== Code Summary ======
# IngestStageContextBase — the base context shared by every stage of the ingest pipeline. Concrete
# stage contexts subclass it to narrow ``input``. Stage-level node of the context hierarchy.

# ====== Internal Project Imports ======
from common_libs2.pipelines import StageContextBase


class IngestStageContextBase(StageContextBase):
    """Base context for every stage of the ingest pipeline."""


__all__ = ["IngestStageContextBase"]
