# ====== Code Summary ======
# The upsert_qdrant step's context — narrows ``input`` to this step's typed input and exposes the
# real Qdrant client it requires as a typed accessor (``ctx.qdrant``). The Qdrant client is
# infrastructure (one real QdrantStorageClient), injected as a service — not abstracted behind a port.

# ====== Internal Project Imports ======
from common_libs.storage.qdrant.client import QdrantStorageClient

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepContextBase
from .io import IngestStageEmbedIndexStepUpsertQdrantInput


class IngestStageEmbedIndexStepUpsertQdrantContext(IngestStageEmbedIndexStepContextBase):
    """Context for the upsert_qdrant step (typed input + the real Qdrant client)."""

    @property
    def input(self) -> IngestStageEmbedIndexStepUpsertQdrantInput:
        """The step's typed input."""
        return self._input

    @property
    def qdrant(self) -> QdrantStorageClient:
        """The Qdrant client the multi-vector points are upserted to."""
        return self.service("qdrant")


__all__ = ["IngestStageEmbedIndexStepUpsertQdrantContext"]
