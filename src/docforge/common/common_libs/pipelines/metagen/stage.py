# ====== Code Summary ======
# The metagen stage — a GROUP wiring its four action nodes (budget_gate -> chunk_scope -> doc_scope ->
# assemble_doc_meta) with ``always`` transitions (a sequence). It generates LLM-derived metadata per
# chunk (chunk-scope ``derived_meta``) and per document (document-scope ``doc_fields``), then assembles
# the merged ``doc_meta`` the embed/index stage consumes. The generation targets + field-type lookup
# are constructor (assembly) args the builder fills from the collection metadata schema; the LLM chain
# + provider cache are injected SERVICES the nodes read. Empty targets = no-op passthrough.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import Chunk, DocumentIR, MetaFieldSpec
from common_libs.pipelines.flow import (
    FromNode,
    FromRunInput,
    GroupNode,
    NodeInput,
    NodeOutput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import (
    MetagenAssembleDocMeta,
    MetagenBudgetGate,
    MetagenChunkScope,
    MetagenDocScope,
)


class MetagenStageInput(NodeInput):
    """
    The metagen stage input.

    Attributes:
        chunks (list[Chunk]): Contextualized chunks (from the contextualize stage).
        ir (DocumentIR): The enriched IR (from the enrich stage) — document-scope digest source.
        doc_user_meta (dict | None): Caller-supplied document metadata (from the run input),
            highest precedence; None when the caller supplied none.
    """

    chunks: Annotated[list[Chunk], FromNode("contextualize", "chunks")]
    ir: Annotated[DocumentIR, FromNode("enrich", "ir")]
    doc_user_meta: Annotated[dict | None, FromRunInput(required=False)]


class MetagenStageOutput(NodeOutput):
    """
    The assembled metagen output consumed by the embed/index stage.

    Attributes:
        chunks (list[Chunk]): The same chunks, with chunk-scope generated values written into each
            ``chunk.derived_meta``.
        doc_meta (dict): The merged document-level metadata (system < generated < user).
    """

    chunks: list[Chunk]
    doc_meta: dict


class MetagenStage(GroupNode):
    """Metagen: budget_gate -> chunk_scope -> doc_scope -> assemble_doc_meta, as a sequence."""

    Input = MetagenStageInput
    Output = MetagenStageOutput

    def __init__(
        self,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
        max_concurrency: int = 8,
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Wire the four metagen nodes as a sequence (``always`` edges).

        Args:
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``; empty disables
                the stage (every node becomes a no-op passthrough). Derived by the assembler from the
                collection metadata schema (not a free-form config knob).
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup for the generated fields,
                keyed by field name. Targets whose field is absent are ignored. Also assembler-derived.
            max_concurrency (int): Maximum concurrent chunk-scope LLM calls.
            max_budget_usd (float): Estimated-cost cap per document (0 = unlimited).
        """
        super().__init__(
            "metagen",
            [
                MetagenBudgetGate("budget_gate", targets, field_types, max_budget_usd),
                MetagenChunkScope("chunk_scope", targets, field_types, max_concurrency),
                MetagenDocScope("doc_scope", targets, field_types),
                MetagenAssembleDocMeta("assemble_doc_meta"),
            ],
            [
                Transition("budget_gate", "chunk_scope"),
                Transition("chunk_scope", "doc_scope"),
                Transition("doc_scope", "assemble_doc_meta"),
            ],
        )

    def assemble(self, outputs: dict, terminal: NodeOutput) -> MetagenStageOutput:
        """
        Narrow the terminal assemble node's output to the stage's downstream contract.

        Args:
            outputs (dict): The four child outputs by id.
            terminal (NodeOutput): The terminal (assemble_doc_meta) output.

        Returns:
            MetagenStageOutput: The chunks (with derived_meta) + the merged doc_meta.
        """
        # 1. The assemble node holds every downstream-facing field; expose chunks + doc_meta.
        return MetagenStageOutput(chunks=terminal.chunks, doc_meta=terminal.doc_meta)


__all__ = ["MetagenStage", "MetagenStageInput", "MetagenStageOutput"]
