# ====== Code Summary ======
# The parse step's context — narrows ``input`` and exposes the parser chain it requires. The chain is
# an injected SERVICE (``parser_chain``): the parse step drives it with one ``call`` per run, the gate
# deciding escalation. The concrete per-collection chain is built at assembly and injected.

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageParseStepContextBase
from .io import IngestStageParseStepParseInput


class IngestStageParseStepParseContext(IngestStageParseStepContextBase):
    """Context for the parse step (typed input + the parser chain service)."""

    @property
    def input(self) -> IngestStageParseStepParseInput:
        """The step's typed input."""
        return self._input

    @property
    def parser_chain(self) -> Chain:
        """The ordered parser escalation chain (docling, ...) the step drives."""
        return self.service("parser_chain")


__all__ = ["IngestStageParseStepParseContext"]
