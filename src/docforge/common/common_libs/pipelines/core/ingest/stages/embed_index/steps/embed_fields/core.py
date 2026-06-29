# ====== Code Summary ======
# IngestStageEmbedIndexStepEmbedFields — the field-embedding step. For each unique metadata field in
# the vector plan (dense or sparse), it resolves that field's per-chunk text value and embeds the
# non-empty ones via the embed chain ONCE, reusing the dense and/or sparse projection for every
# vector that references the field. Results are scattered back per chunk (None where the chunk has no
# value). Declares the embed chain as its only required service; the batch size is a construction config.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef
from common_libs.search.field_index import FieldIndexHelpers

# ====== Local Project Imports ======
from ...helpers_embed import IngestStageEmbedIndexEmbedHelpers
from ..base import IngestStageEmbedIndexStepBase
from .context import IngestStageEmbedIndexStepEmbedFieldsContext
from .errors import IngestStageEmbedIndexStepEmbedFieldsError
from .io import (
    IngestStageEmbedIndexStepEmbedFieldsInput,
    IngestStageEmbedIndexStepEmbedFieldsOutput,
)


class IngestStageEmbedIndexStepEmbedFields(IngestStageEmbedIndexStepBase):
    """
    Embed each unique metadata field's per-chunk value once via the embed chain.

    Reads ``plan`` / ``index_chunks`` / ``doc_meta``; writes the per-field dense/sparse vectors + the
    chain traces. A field in both the dense and sparse plans is embedded a single time.
    """

    SPEC = NodeSpec(
        key="embed_fields",
        name="Embed fields",
        description="Embed each metadata field's per-chunk value once for its named vectors.",
    )
    Input = IngestStageEmbedIndexStepEmbedFieldsInput
    Output = IngestStageEmbedIndexStepEmbedFieldsOutput
    Context = IngestStageEmbedIndexStepEmbedFieldsContext
    Error = IngestStageEmbedIndexStepEmbedFieldsError
    REQUIRES = (ServiceRef(name="embed_chain", description="Ordered embed provider chain."),)

    def __init__(self, embed_batch_size: int) -> None:
        """
        Wire the step with its embed batch size.

        Args:
            embed_batch_size (int): Texts sent per embed chain attempt.
        """
        super().__init__()
        self._embed_batch_size = embed_batch_size

    async def execute(
        self, ctx: IngestStageEmbedIndexStepEmbedFieldsContext
    ) -> IngestStageEmbedIndexStepEmbedFieldsOutput:
        """
        Embed each unique metadata field's per-chunk value and scatter the vectors back.

        Args:
            ctx (IngestStageEmbedIndexStepEmbedFieldsContext): Typed input + the embed chain.

        Returns:
            IngestStageEmbedIndexStepEmbedFieldsOutput: Per-field dense/sparse vectors + chain traces.

        Raises:
            IngestStageEmbedIndexStepEmbedFieldsError: When the embed chain exhausts under
                failure_policy="raise" (propagated from the chain).
        """
        # 1. Collect the unique field names across the dense + sparse plans (each embedded once).
        plan = ctx.input.plan
        index_chunks = ctx.input.index_chunks
        doc_meta = ctx.input.doc_meta or {}
        field_names: list[str] = []
        for fv in [*plan.dense, *plan.sparse]:
            if fv.name not in field_names:
                field_names.append(fv.name)

        # 2. Resolve + embed each field's per-chunk value, accumulating the per-batch traces.
        field_dense: dict[str, list[list[float] | None]] = {}
        field_sparse: dict[str, list[dict[int, float] | None]] = {}
        traces = []
        for name in field_names:
            values = [
                FieldIndexHelpers.resolve_field_text(name, c, doc_meta) for c in index_chunks
            ]
            dense, sparse, field_traces = await IngestStageEmbedIndexEmbedHelpers.embed_values(
                ctx.embed_chain, values, self._embed_batch_size
            )
            field_dense[name] = dense
            field_sparse[name] = sparse
            traces.extend(field_traces)
        self.logger.info(f"Embed fields: fields={len(field_names)} batches={len(traces)}")

        # 3. Hand the per-field vectors + traces to the assemble / persist steps.
        return IngestStageEmbedIndexStepEmbedFieldsOutput(
            field_dense=field_dense,
            field_sparse=field_sparse,
            field_traces=traces,
        )


__all__ = ["IngestStageEmbedIndexStepEmbedFields"]
