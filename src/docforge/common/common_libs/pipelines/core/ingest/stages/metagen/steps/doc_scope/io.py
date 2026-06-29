# ====== Code Summary ======
# IO contract for the document-scope step: it reads the IR from the parent stage input and the proceed
# flag from the budget-gate sibling, and produces the document-scope generated values (doc_fields),
# the count generated, and one chain trace. When proceed is False it returns empty doc_fields.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import ChainTrace, DocumentIR
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput


class IngestStageMetagenStepDocScopeInput(NodeInput):
    """
    Input of the document-scope step.

    Attributes:
        ir (DocumentIR): The final IR (from the parent stage input) — digest source.
        proceed (bool): The budget-gate decision (from the budget-gate step).
    """

    ir: Annotated[DocumentIR, FromParent()]
    proceed: Annotated[bool, FromSibling(producer="budget_gate", field="proceed")]


class IngestStageMetagenStepDocScopeOutput(NodeOutput):
    """
    Output of the document-scope step.

    Attributes:
        doc_fields (dict): Document-scope generated values ``{field_name: value}``.
        n_generated (int): Count of document-scope generated values written.
        chain_trace (ChainTrace | None): The document-scope chain trace, or None when nothing ran.
    """

    doc_fields: dict = {}
    n_generated: int = 0
    chain_trace: ChainTrace | None = None


__all__ = [
    "IngestStageMetagenStepDocScopeInput",
    "IngestStageMetagenStepDocScopeOutput",
]
