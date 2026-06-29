# ====== Code Summary ======
# The ingest pipeline's context — the top of this pipeline's context hierarchy. It narrows ``input``
# to the run input; descendants link to it via ``ctx.parent``.

# ====== Internal Project Imports ======
from common_libs2.pipelines import PipelineContextBase

# ====== Local Project Imports ======
from .io import IngestInput


class IngestContext(PipelineContextBase):
    """Context for the ingest pipeline (typed run input)."""

    @property
    def input(self) -> IngestInput:
        """The pipeline run input."""
        return self._input


__all__ = ["IngestContext"]
