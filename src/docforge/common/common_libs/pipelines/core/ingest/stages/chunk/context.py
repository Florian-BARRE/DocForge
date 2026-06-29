# ====== Code Summary ======
# The chunk stage's context — narrows ``input`` to the stage input. The stage itself requires no
# service (its step is a pure constructor-injected chunker); this context exists for hierarchy +
# typed input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageChunkInput


class IngestStageChunkContext(IngestStageContextBase):
    """Context for the chunk stage (typed input)."""

    @property
    def input(self) -> IngestStageChunkInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageChunkContext"]
