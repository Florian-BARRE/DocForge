# ====== Code Summary ======
# The embed_fields node — the field-embedding action. For each unique metadata field in the vector
# plan (dense or sparse), it resolves that field's per-chunk text value and embeds the non-empty ones
# via the embed chain ONCE, reusing the dense and/or sparse projection for every vector that references
# the field. Results are scattered back per chunk (None where the chunk has no value). The embed chain
# is an injected service; the batch size is a construction-time argument.

# ====== Standard Library Imports ======
from typing import Annotated, Any

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
from common_libs.search.field_index import FieldIndexHelpers, VectorPlan

# ====== Local Project Imports ======
from ..helpers_embed import EmbedIndexEmbedHelpers


class EmbedIndexEmbedFieldsInput(NodeInput):
    """
    Input of the embed_fields node.

    Attributes:
        plan (VectorPlan): The named dense/sparse vectors the schema requires (from plan_vectors).
        index_chunks (list[Chunk]): Indexable chunks (from plan_vectors) whose field values are embedded.
        doc_meta (dict | None): Document-level field values (from the enclosing stage input).
    """

    plan: Annotated[VectorPlan, FromNode("plan_vectors", "plan")]
    index_chunks: Annotated[list[Chunk], FromNode("plan_vectors", "index_chunks")]
    doc_meta: Annotated[dict[str, Any] | None, FromGroupInput()]


class EmbedIndexEmbedFieldsOutput(NodeOutput):
    """
    Output of the embed_fields node.

    Attributes:
        field_dense (dict): Field name -> per-chunk dense vectors (None where the chunk has no value).
        field_sparse (dict): Field name -> per-chunk sparse vectors (None where the chunk has no value).
        field_traces (list[ChainTrace]): One embed chain trace per batch actually embedded.
    """

    field_dense: dict[str, list[list[float] | None]]
    field_sparse: dict[str, list[dict[int, float] | None]]
    field_traces: list[ChainTrace]


class EmbedIndexEmbedFields(ActionNode):
    """
    Embed each unique metadata field's per-chunk value once via the embed chain.

    Reads ``plan`` / ``index_chunks`` / ``doc_meta``; writes the per-field dense/sparse vectors + the
    chain traces. A field in both the dense and sparse plans is embedded a single time.
    """

    Input = EmbedIndexEmbedFieldsInput
    Output = EmbedIndexEmbedFieldsOutput

    def __init__(self, node_id: str, embed_batch_size: int) -> None:
        """
        Wire the node with its embed batch size.

        Args:
            node_id (str): The node's id (unique among its siblings).
            embed_batch_size (int): Texts sent per embed chain attempt.
        """
        super().__init__(node_id)
        self._embed_batch_size = embed_batch_size

    async def execute(self, ctx: Context) -> EmbedIndexEmbedFieldsOutput:
        """
        Embed each unique metadata field's per-chunk value and scatter the vectors back.

        Args:
            ctx (Context): The resolved input + the injected embed chain service.

        Returns:
            EmbedIndexEmbedFieldsOutput: Per-field dense/sparse vectors + chain traces.

        Raises:
            ChainExhaustedError: When the embed chain exhausts under failure_policy="raise".
        """
        # 1. Collect the unique field names across the dense + sparse plans (each embedded once).
        plan = ctx.input.plan
        index_chunks = ctx.input.index_chunks
        doc_meta = ctx.input.doc_meta or {}
        chain = ctx.service("embed_chain")
        field_names: list[str] = []
        for fv in [*plan.dense, *plan.sparse]:
            if fv.name not in field_names:
                field_names.append(fv.name)

        # 2. Resolve + embed each field's per-chunk value, accumulating the per-batch traces.
        field_dense: dict[str, list[list[float] | None]] = {}
        field_sparse: dict[str, list[dict[int, float] | None]] = {}
        traces: list[ChainTrace] = []
        for name in field_names:
            values = [FieldIndexHelpers.resolve_field_text(name, c, doc_meta) for c in index_chunks]
            dense, sparse, field_traces = await EmbedIndexEmbedHelpers.embed_values(
                chain, values, self._embed_batch_size
            )
            field_dense[name] = dense
            field_sparse[name] = sparse
            traces.extend(field_traces)
        self.logger.info(f"Embed fields: fields={len(field_names)} batches={len(traces)}")

        # 3. Hand the per-field vectors + traces to the assemble / persist nodes.
        return EmbedIndexEmbedFieldsOutput(
            field_dense=field_dense,
            field_sparse=field_sparse,
            field_traces=traces,
        )


__all__ = ["EmbedIndexEmbedFields", "EmbedIndexEmbedFieldsInput", "EmbedIndexEmbedFieldsOutput"]
