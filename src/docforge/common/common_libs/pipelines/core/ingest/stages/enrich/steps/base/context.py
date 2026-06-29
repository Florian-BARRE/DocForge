# ====== Code Summary ======
# IngestStageEnrichStepContextBase - the base context shared by every step of the enrich stage.
# Concrete step contexts subclass it to narrow ``input`` and add typed service accessors (chains,
# object store, provider cache). It is the step-level node of the context hierarchy for this stage.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepContextBase


class IngestStageEnrichStepContextBase(StepContextBase):
    """Base context for every step of the enrich stage."""


__all__ = ["IngestStageEnrichStepContextBase"]
