# ====== Code Summary ======
# IngestStageIngestStepContextBase — the base context shared by every step of the ingest stage.
# Concrete step contexts subclass it to narrow ``input`` and add typed service accessors. It is the
# step-level node of the context hierarchy for this stage.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepContextBase


class IngestStageIngestStepContextBase(StepContextBase):
    """Base context for every step of the ingest stage."""


__all__ = ["IngestStageIngestStepContextBase"]
