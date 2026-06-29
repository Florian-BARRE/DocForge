# ====== Code Summary ======
# IngestStageMetagenStepContextBase — the base context shared by every step of the metagen stage.
# Concrete step contexts subclass it to narrow ``input`` and add typed service accessors (the LLM
# chain + the provider cache). It is the step-level node of the context hierarchy for this stage.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepContextBase


class IngestStageMetagenStepContextBase(StepContextBase):
    """Base context for every step of the metagen stage."""


__all__ = ["IngestStageMetagenStepContextBase"]
