# ====== Code Summary ======
# The enrich stage's context - narrows ``input`` to the stage input. The stage itself requires no
# service (its steps declare theirs); this context exists for hierarchy + typed input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageEnrichInput


class IngestStageEnrichContext(IngestStageContextBase):
    """Context for the enrich stage (typed input)."""

    @property
    def input(self) -> IngestStageEnrichInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageEnrichContext"]
