# ====== Code Summary ======
# The parse stage's context — narrows ``input`` to the stage input. The stage itself requires no
# service (its steps declare theirs; the parser chain signature used by the node fingerprint is held
# on the stage instance, not resolved from the registry). This context exists for hierarchy + typed
# input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageParseInput


class IngestStageParseContext(IngestStageContextBase):
    """Context for the parse stage (typed input)."""

    @property
    def input(self) -> IngestStageParseInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageParseContext"]
