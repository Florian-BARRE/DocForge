# ====== Code Summary ======
# IngestStageEmbedIndexStepPersistChunks — the persistence step. It opens a Postgres session LOCALLY
# from the injected client, bulk-inserts ALL chunks (parents included, for hydration; idempotent
# upsert), and assembles the final embed_index result (counts + per-field vector count + the combined
# embed chain traces). It preserves the legacy no-op guard: an EMPTY chunk set persists nothing and
# returns a zero result with no field-vector count and no traces. Declares Postgres as its only service.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef
from common_libs.storage.postgres.repositories.chunk_repo import ChunkRepository

# ====== Local Project Imports ======
from ...result import IngestStageEmbedIndexResult
from ..base import IngestStageEmbedIndexStepBase
from .context import IngestStageEmbedIndexStepPersistChunksContext
from .errors import IngestStageEmbedIndexStepPersistChunksError
from .io import (
    IngestStageEmbedIndexStepPersistChunksInput,
    IngestStageEmbedIndexStepPersistChunksOutput,
)


class IngestStageEmbedIndexStepPersistChunks(IngestStageEmbedIndexStepBase):
    """
    Persist all chunks to Postgres and assemble the final embed_index result.

    Reads all chunks + the index/plan/upsert/trace siblings; writes the assembled result. An empty
    chunk set persists nothing and returns a zero result (legacy parity).
    """

    SPEC = NodeSpec(
        key="persist_chunks",
        name="Persist chunks",
        description="Bulk-insert all chunks to Postgres (idempotent) + assemble the embed result.",
    )
    Input = IngestStageEmbedIndexStepPersistChunksInput
    Output = IngestStageEmbedIndexStepPersistChunksOutput
    Context = IngestStageEmbedIndexStepPersistChunksContext
    Error = IngestStageEmbedIndexStepPersistChunksError
    REQUIRES = (ServiceRef(name="postgres", description="Postgres session factory client."),)

    def __init__(self) -> None:
        """Build the step with its own (stateless) chunk repository."""
        super().__init__()
        self._chunk_repo = ChunkRepository()

    async def execute(
        self, ctx: IngestStageEmbedIndexStepPersistChunksContext
    ) -> IngestStageEmbedIndexStepPersistChunksOutput:
        """
        Persist all chunks and assemble the embed_index result.

        Args:
            ctx (IngestStageEmbedIndexStepPersistChunksContext): Typed input + the Postgres client.

        Returns:
            IngestStageEmbedIndexStepPersistChunksOutput: The assembled embed_index result.

        Raises:
            IngestStageEmbedIndexStepPersistChunksError: When the chunk persistence fails.
        """
        data = ctx.input

        # 1. No-op guard: an empty chunk set persists nothing and returns a zero result (legacy
        #    parity — no session, no field-vector count, no traces).
        if not data.chunks:
            self.logger.info(
                f"Persist chunks: no chunks - skipping (collection={data.collection_id!r})."
            )
            return IngestStageEmbedIndexStepPersistChunksOutput(
                embed_result=IngestStageEmbedIndexResult(
                    n_embedded=0,
                    n_upserted_qdrant=0,
                    n_inserted_postgres=0,
                    collection_name=data.collection_id,
                )
            )

        # 2. Bulk-insert ALL chunks (parents included) in a local transactional session.
        try:
            async with ctx.postgres.session() as session:
                await self._chunk_repo.bulk_insert(session, data.chunks)
        except Exception as exc:
            self.logger.error(f"Chunk persistence failed: {exc}")
            raise IngestStageEmbedIndexStepPersistChunksError(
                "Failed to persist chunks to Postgres.",
                node_key=self.key,
                cause=exc,
            ) from exc

        # 3. Assemble the final result (combined embed traces, in content-then-fields order).
        n_field_vectors = len(data.plan.dense) + len(data.plan.sparse)
        result = IngestStageEmbedIndexResult(
            n_embedded=len(data.index_chunks),
            n_upserted_qdrant=data.n_upserted,
            n_inserted_postgres=len(data.chunks),
            collection_name=data.collection_id,
            n_field_vectors=n_field_vectors,
            chain_traces=[*data.content_traces, *data.field_traces],
        )
        self.logger.info(
            f"Persist chunks: persisted={len(data.chunks)} embedded={result.n_embedded} "
            f"field_vectors={n_field_vectors} collection={data.collection_id!r}"
        )
        return IngestStageEmbedIndexStepPersistChunksOutput(embed_result=result)


__all__ = ["IngestStageEmbedIndexStepPersistChunks"]
