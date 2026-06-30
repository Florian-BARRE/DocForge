# ====== Code Summary ======
# The upsert_qdrant node — the Qdrant indexing action. It ensures the collection carries every named
# vector the schema needs (sized by the embed dimension), then upserts the lean multi-vector points
# (idempotent by chunk id). It preserves the legacy no-op guard: an EMPTY chunk set performs no
# ensure_collection / upsert side effect and returns a zero count. The Qdrant client is an injected
# service.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)
from common_libs.search.field_index import VectorPlan


class EmbedIndexUpsertQdrantInput(NodeInput):
    """
    Input of the upsert_qdrant node.

    Attributes:
        collection_id (str | None): Target Qdrant collection (from the stage input). The stage is
            gated so this is a real collection when it runs; bound nullable for purity.
        chunks (list[Chunk]): All chunks (from the stage input) — drives the no-op guard: an empty
            chunk set skips ensure_collection + upsert entirely (legacy parity).
        plan (VectorPlan): The named dense/sparse vector plan (from plan_vectors) — collection schema.
        dimension (int): Dense vector dimension (from embed_content) — collection schema.
        chunk_ids (list[str]): Point ids to upsert (from assemble_points).
        dense_by_vector (dict): Named-vector key -> per-chunk dense vectors (from assemble_points).
        sparse_by_vector (dict): Named-vector key -> per-chunk sparse vectors (from assemble_points).
        payloads (list[dict]): Per-chunk filterable payloads (from assemble_points).
    """

    collection_id: Annotated[str | None, FromGroupInput()]
    chunks: Annotated[list[Chunk], FromGroupInput()]
    plan: Annotated[VectorPlan, FromNode("plan_vectors", "plan")]
    dimension: Annotated[int, FromNode("embed_content", "dimension")]
    chunk_ids: Annotated[list[str], FromNode("assemble_points", "chunk_ids")]
    dense_by_vector: Annotated[
        dict[str, list[list[float] | None]], FromNode("assemble_points", "dense_by_vector")
    ]
    sparse_by_vector: Annotated[
        dict[str, list[dict[int, float] | None]], FromNode("assemble_points", "sparse_by_vector")
    ]
    payloads: Annotated[list[dict[str, Any]], FromNode("assemble_points", "payloads")]


class EmbedIndexUpsertQdrantOutput(NodeOutput):
    """
    Output of the upsert_qdrant node.

    Attributes:
        n_upserted (int): Number of points upserted to Qdrant (0 when there were no chunks).
        collection_name (str | None): The Qdrant collection the points were upserted into.
    """

    n_upserted: int
    collection_name: str | None


class EmbedIndexUpsertQdrant(ActionNode):
    """
    Ensure the collection + upsert the multi-vector points to Qdrant (idempotent).

    Reads the collection id + plan + dimension + assembled points; writes the upsert count. An empty
    chunk set is a no-op (no ensure_collection / upsert), matching the legacy early return.
    """

    Input = EmbedIndexUpsertQdrantInput
    Output = EmbedIndexUpsertQdrantOutput

    async def execute(self, ctx: Context) -> EmbedIndexUpsertQdrantOutput:
        """
        Ensure the collection and upsert the multi-vector points.

        Args:
            ctx (Context): The resolved input + the injected Qdrant client service.

        Returns:
            EmbedIndexUpsertQdrantOutput: Upsert count + collection name.
        """
        data = ctx.input
        collection = data.collection_id
        qdrant = ctx.service("qdrant")

        # 1. No-op guard: an empty chunk set skips ensure_collection + upsert (legacy parity).
        if not data.chunks:
            self.logger.info(f"Upsert Qdrant: no chunks - skipping (collection={collection!r}).")
            return EmbedIndexUpsertQdrantOutput(n_upserted=0, collection_name=collection)

        # 2. Ensure the collection carries every named vector the schema needs, then upsert.
        await qdrant.ensure_collection(
            collection,
            dense_dim=data.dimension,
            field_dense_names=data.plan.dense_vector_names,
            field_sparse_names=data.plan.sparse_vector_names,
        )
        n_upserted = await qdrant.upsert_points(
            collection_name=collection,
            chunk_ids=data.chunk_ids,
            dense_by_vector=data.dense_by_vector,
            sparse_by_vector=data.sparse_by_vector,
            payloads=data.payloads,
        )
        self.logger.info(f"Upsert Qdrant: upserted={n_upserted} collection={collection!r}")

        # 3. Hand the upsert count to the persist node (which assembles the final result).
        return EmbedIndexUpsertQdrantOutput(n_upserted=n_upserted, collection_name=collection)


__all__ = ["EmbedIndexUpsertQdrant", "EmbedIndexUpsertQdrantInput", "EmbedIndexUpsertQdrantOutput"]
