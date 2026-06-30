# ====== Code Summary ======
# The persist_chunks node — the persistence action (terminal of the embed_index stage). It opens a
# Postgres session LOCALLY from the injected client, bulk-inserts ALL chunks (parents included, for
# hydration; idempotent upsert), and assembles the final embed_index result (counts + per-field vector
# count + the combined embed chain traces). It preserves the legacy no-op guard: an EMPTY chunk set
# persists nothing and returns a zero result. The Postgres client is an injected service.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import ChainTrace
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)
from common_libs.search.field_index import VectorPlan
from common_libs.storage.postgres.repositories.chunk_repo import ChunkRepository

# ====== Local Project Imports ======
from ..result import EmbedIndexResult


class EmbedIndexPersistChunksInput(NodeInput):
    """
    Input of the persist_chunks node.

    Attributes:
        chunks (list[Chunk]): All chunks (parents included) to persist to Postgres.
        collection_id (str | None): Target collection (carried into the result).
        index_chunks (list[Chunk]): Indexed chunks (from plan_vectors) — drives the embedded count.
        plan (VectorPlan): The vector plan (from plan_vectors) — drives the field-vector count.
        n_upserted (int): Points upserted to Qdrant (from upsert_qdrant) — orders persist after upsert.
        content_traces (list[ChainTrace]): Content embed batch traces (from embed_content).
        field_traces (list[ChainTrace]): Field embed batch traces (from embed_fields).
    """

    chunks: Annotated[list[Chunk], FromGroupInput()]
    collection_id: Annotated[str | None, FromGroupInput()]
    index_chunks: Annotated[list[Chunk], FromNode("plan_vectors", "index_chunks")]
    plan: Annotated[VectorPlan, FromNode("plan_vectors", "plan")]
    n_upserted: Annotated[int, FromNode("upsert_qdrant", "n_upserted")]
    content_traces: Annotated[list[ChainTrace], FromNode("embed_content", "content_traces")]
    field_traces: Annotated[list[ChainTrace], FromNode("embed_fields", "field_traces")]


class EmbedIndexPersistChunksOutput(NodeOutput):
    """
    Output of the persist_chunks node.

    Attributes:
        embed_result (EmbedIndexResult): The assembled embed + index result (counts + target
            collection + per-field vector count + per-batch embed chain traces).
    """

    embed_result: EmbedIndexResult


class EmbedIndexPersistChunks(ActionNode):
    """
    Persist all chunks to Postgres and assemble the final embed_index result.

    Reads all chunks + the index/plan/upsert/trace siblings; writes the assembled result. An empty
    chunk set persists nothing and returns a zero result (legacy parity).
    """

    Input = EmbedIndexPersistChunksInput
    Output = EmbedIndexPersistChunksOutput

    def __init__(self, node_id: str) -> None:
        """
        Build the node with its own (stateless) chunk repository.

        Args:
            node_id (str): The node's id (unique among its siblings).
        """
        super().__init__(node_id)
        self._chunk_repo = ChunkRepository()

    async def execute(self, ctx: Context) -> EmbedIndexPersistChunksOutput:
        """
        Persist all chunks and assemble the embed_index result.

        Args:
            ctx (Context): The resolved input + the injected Postgres client service.

        Returns:
            EmbedIndexPersistChunksOutput: The assembled embed_index result.
        """
        data = ctx.input

        # 1. No-op guard: an empty chunk set persists nothing and returns a zero result (legacy
        #    parity — no session, no field-vector count, no traces).
        if not data.chunks:
            self.logger.info(
                f"Persist chunks: no chunks - skipping (collection={data.collection_id!r})."
            )
            return EmbedIndexPersistChunksOutput(
                embed_result=EmbedIndexResult(
                    n_embedded=0,
                    n_upserted_qdrant=0,
                    n_inserted_postgres=0,
                    collection_name=data.collection_id,
                )
            )

        # 2. Bulk-insert ALL chunks (parents included) in a local transactional session.
        postgres = ctx.service("postgres")
        async with postgres.session() as session:
            await self._chunk_repo.bulk_insert(session, data.chunks)

        # 3. Assemble the final result (combined embed traces, in content-then-fields order).
        n_field_vectors = len(data.plan.dense) + len(data.plan.sparse)
        result = EmbedIndexResult(
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
        return EmbedIndexPersistChunksOutput(embed_result=result)


__all__ = [
    "EmbedIndexPersistChunks",
    "EmbedIndexPersistChunksInput",
    "EmbedIndexPersistChunksOutput",
]
