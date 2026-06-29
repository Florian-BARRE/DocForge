# ====== Code Summary ======
# The ingest stage's context — narrows ``input`` to the stage input. The stage itself requires no
# service (its steps declare theirs); this context exists for hierarchy + typed input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageIngestInput


class IngestStageIngestContext(IngestStageContextBase):
    """Context for the ingest stage (typed input)."""

    @property
    def input(self) -> IngestStageIngestInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageIngestContext"]
