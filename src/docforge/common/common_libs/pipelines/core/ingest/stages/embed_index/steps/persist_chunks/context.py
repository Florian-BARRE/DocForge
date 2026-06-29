# ====== Code Summary ======
# The persist_chunks step's context — narrows ``input`` to this step's typed input and exposes the
# real Postgres client it requires as a typed accessor (``ctx.postgres``). The step opens a session
# LOCALLY from this client so it never outlives the step; the client is injected as a service.

# ====== Internal Project Imports ======
from common_libs.storage.postgres.client import PostgresClient

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepContextBase
from .io import IngestStageEmbedIndexStepPersistChunksInput


class IngestStageEmbedIndexStepPersistChunksContext(IngestStageEmbedIndexStepContextBase):
    """Context for the persist_chunks step (typed input + the real Postgres client)."""

    @property
    def input(self) -> IngestStageEmbedIndexStepPersistChunksInput:
        """The step's typed input."""
        return self._input

    @property
    def postgres(self) -> PostgresClient:
        """The Postgres client a transactional session is opened from for chunk persistence."""
        return self.service("postgres")


__all__ = ["IngestStageEmbedIndexStepPersistChunksContext"]
