# ====== Code Summary ======
# IO contract for the assemble-doc-meta step: it gathers the chunk-scope chunks/count/trace, the
# document-scope fields/count/trace, the budget-gate cost estimate (all via FromSibling), plus the IR
# + implicit_meta + doc_user_meta from the parent stage input, and produces the stage's downstream
# artefacts: the chunks, the doc_fields, the merged doc_meta, and the metagen result record.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, ChainTrace, DocumentIR
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...result import IngestStageMetagenResult


class IngestStageMetagenStepAssembleDocMetaInput(NodeInput):
    """
    Input of the assemble-doc-meta step.

    Attributes:
        chunks (list[Chunk]): The chunk-scope chunks (with derived_meta filled).
        chunk_n_generated (int): Count of chunk-scope generated values.
        chunk_trace (ChainTrace | None): The chunk-scope chain trace, if any.
        doc_fields (dict): The document-scope generated values.
        doc_n_generated (int): Count of document-scope generated values.
        doc_trace (ChainTrace | None): The document-scope chain trace, if any.
        est_cost_usd (float): The budget-gate cost estimate.
        ir (DocumentIR): The final IR (system-field source for doc_meta).
        implicit_meta (dict): File-intrinsic metadata (lowest precedence in doc_meta).
        doc_user_meta (dict | None): Caller-supplied metadata (highest precedence in doc_meta).
    """

    chunks: Annotated[list[Chunk], FromSibling(producer="chunk_scope", field="chunks")]
    chunk_n_generated: Annotated[int, FromSibling(producer="chunk_scope", field="n_generated")]
    chunk_trace: Annotated[
        ChainTrace | None, FromSibling(producer="chunk_scope", field="chain_trace", required=False)
    ]
    doc_fields: Annotated[dict, FromSibling(producer="doc_scope", field="doc_fields")]
    doc_n_generated: Annotated[int, FromSibling(producer="doc_scope", field="n_generated")]
    doc_trace: Annotated[
        ChainTrace | None, FromSibling(producer="doc_scope", field="chain_trace", required=False)
    ]
    est_cost_usd: Annotated[float, FromSibling(producer="budget_gate", field="est_cost_usd")]
    ir: Annotated[DocumentIR, FromParent()]
    implicit_meta: Annotated[dict, FromParent()]
    doc_user_meta: Annotated[dict | None, FromParent(required=False)]


class IngestStageMetagenStepAssembleDocMetaOutput(NodeOutput):
    """
    Output of the assemble-doc-meta step — the stage's downstream artefacts.

    Attributes:
        chunks (list[Chunk]): The same chunks (with chunk-scope derived_meta filled).
        doc_fields (dict): The document-scope generated values.
        doc_meta (dict): The merged document-level metadata (implicit < generated < user).
        metagen_result (IngestStageMetagenResult): Counts, estimated cost, and chain traces.
    """

    chunks: list[Chunk]
    doc_fields: dict
    doc_meta: dict
    metagen_result: IngestStageMetagenResult


__all__ = [
    "IngestStageMetagenStepAssembleDocMetaInput",
    "IngestStageMetagenStepAssembleDocMetaOutput",
]
