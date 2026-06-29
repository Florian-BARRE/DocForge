# ====== Code Summary ======
# IngestStageEmbedIndexStepUpsertQdrant — the Qdrant indexing step. It ensures the collection carries
# every named vector the schema needs (sized by the embed dimension), then upserts the lean
# multi-vector points (idempotent by chunk id). It preserves the legacy no-op guard: an EMPTY chunk
# set performs no ensure_collection / upsert side effect and returns a zero count. Declares the Qdrant
# client as its only required service.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepBase
from .context import IngestStageEmbedIndexStepUpsertQdrantContext
from .errors import IngestStageEmbedIndexStepUpsertQdrantError
from .io import (
    IngestStageEmbedIndexStepUpsertQdrantInput,
    IngestStageEmbedIndexStepUpsertQdrantOutput,
)


class IngestStageEmbedIndexStepUpsertQdrant(IngestStageEmbedIndexStepBase):
    """
    Ensure the collection + upsert the multi-vector points to Qdrant (idempotent).

    Reads the collection id + plan + dimension + assembled points; writes the upsert count. An empty
    chunk set is a no-op (no ensure_collection / upsert), matching the legacy early return.
    """

    SPEC = NodeSpec(
        key="upsert_qdrant",
        name="Upsert Qdrant",
        description="Ensure the collection schema + upsert the multi-vector points (idempotent).",
    )
    Input = IngestStageEmbedIndexStepUpsertQdrantInput
    Output = IngestStageEmbedIndexStepUpsertQdrantOutput
    Context = IngestStageEmbedIndexStepUpsertQdrantContext
    Error = IngestStageEmbedIndexStepUpsertQdrantError
    REQUIRES = (ServiceRef(name="qdrant", description="Qdrant multi-vector storage client."),)

    async def execute(
        self, ctx: IngestStageEmbedIndexStepUpsertQdrantContext
    ) -> IngestStageEmbedIndexStepUpsertQdrantOutput:
        """
        Ensure the collection and upsert the multi-vector points.

        Args:
            ctx (IngestStageEmbedIndexStepUpsertQdrantContext): Typed input + the Qdrant client.

        Returns:
            IngestStageEmbedIndexStepUpsertQdrantOutput: Upsert count + collection name.

        Raises:
            IngestStageEmbedIndexStepUpsertQdrantError: When ensure_collection / upsert fails.
        """
        data = ctx.input
        collection = data.collection_id

        # 1. No-op guard: an empty chunk set skips ensure_collection + upsert (legacy parity).
        if not data.chunks:
            self.logger.info(f"Upsert Qdrant: no chunks - skipping (collection={collection!r}).")
            return IngestStageEmbedIndexStepUpsertQdrantOutput(
                n_upserted=0, collection_name=collection
            )

        # 2. Ensure the collection carries every named vector the schema needs, then upsert.
        try:
            await ctx.qdrant.ensure_collection(
                collection,
                dense_dim=data.dimension,
                field_dense_names=data.plan.dense_vector_names,
                field_sparse_names=data.plan.sparse_vector_names,
            )
            n_upserted = await ctx.qdrant.upsert_points(
                collection_name=collection,
                chunk_ids=data.chunk_ids,
                dense_by_vector=data.dense_by_vector,
                sparse_by_vector=data.sparse_by_vector,
                payloads=data.payloads,
            )
        except Exception as exc:
            self.logger.error(f"Qdrant upsert failed for collection {collection!r}: {exc}")
            raise IngestStageEmbedIndexStepUpsertQdrantError(
                f"Failed to upsert points to Qdrant collection {collection!r}.",
                node_key=self.key,
                cause=exc,
            ) from exc

        self.logger.info(f"Upsert Qdrant: upserted={n_upserted} collection={collection!r}")

        # 3. Hand the upsert count to the persist step (which assembles the final result).
        return IngestStageEmbedIndexStepUpsertQdrantOutput(
            n_upserted=n_upserted, collection_name=collection
        )


__all__ = ["IngestStageEmbedIndexStepUpsertQdrant"]
