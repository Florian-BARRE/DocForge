# ====== Code Summary ======
# The metagen stage's context — narrows ``input`` to the stage input. The stage itself requires no
# service (its steps declare theirs); this context exists for hierarchy + typed input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageMetagenInput


class IngestStageMetagenContext(IngestStageContextBase):
    """Context for the metagen stage (typed input)."""

    @property
    def input(self) -> IngestStageMetagenInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageMetagenContext"]
