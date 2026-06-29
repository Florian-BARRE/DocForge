# ====== Code Summary ======
# The embed_fields step's context — narrows ``input`` to this step's typed input and exposes the
# embed chain it requires as a typed accessor (``ctx.embed_chain``). The chain is built per-collection
# at assembly and injected as a service.

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepContextBase
from .io import IngestStageEmbedIndexStepEmbedFieldsInput


class IngestStageEmbedIndexStepEmbedFieldsContext(IngestStageEmbedIndexStepContextBase):
    """Context for the embed_fields step (typed input + the embed chain)."""

    @property
    def input(self) -> IngestStageEmbedIndexStepEmbedFieldsInput:
        """The step's typed input."""
        return self._input

    @property
    def embed_chain(self) -> Chain:
        """The ordered embed chain the metadata field values are embedded through."""
        return self.service("embed_chain")


__all__ = ["IngestStageEmbedIndexStepEmbedFieldsContext"]
