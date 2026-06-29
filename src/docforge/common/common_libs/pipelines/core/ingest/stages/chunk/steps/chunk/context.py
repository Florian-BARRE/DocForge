# ====== Code Summary ======
# The chunk step's context — narrows ``input`` to this step's typed input. The chunking engine is a
# pure constructor-injected collaborator (no service), so the context only carries typed input.

# ====== Local Project Imports ======
from ..base import IngestStageChunkStepContextBase
from .io import IngestStageChunkStepChunkInput


class IngestStageChunkStepChunkContext(IngestStageChunkStepContextBase):
    """Context for the chunk step (typed input only)."""

    @property
    def input(self) -> IngestStageChunkStepChunkInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageChunkStepChunkContext"]
