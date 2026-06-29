# ====== Code Summary ======
# The embed_index stage's context — narrows ``input`` to the stage input. The stage itself requires
# no service (its steps declare theirs); this context exists for hierarchy + typed input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageEmbedIndexInput


class IngestStageEmbedIndexContext(IngestStageContextBase):
    """Context for the embed_index stage (typed input)."""

    @property
    def input(self) -> IngestStageEmbedIndexInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageEmbedIndexContext"]
