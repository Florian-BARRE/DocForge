# ====== Code Summary ======
# IngestStageMetagenStepAssembleDocMeta — the final metagen step. As the stage that holds every
# document-level input, it assembles the merged ``doc_meta`` so the IO graph is closed (the embed/index
# stage consumes doc_meta). The merge precedence is preserved exactly from the legacy s456_runner:
# file-intrinsic implicit_meta + IR-derived system fields < generated doc_fields < user doc_user_meta —
# a user value always wins over a generated one, which wins over an implicit one. It also folds the two
# scope outputs (counts + traces) and the budget-gate estimate into the metagen result record.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec

# ====== Local Project Imports ======
from ...result import IngestStageMetagenResult
from ..base import IngestStageMetagenStepBase
from .context import IngestStageMetagenStepAssembleDocMetaContext
from .errors import IngestStageMetagenStepAssembleDocMetaError
from .io import (
    IngestStageMetagenStepAssembleDocMetaInput,
    IngestStageMetagenStepAssembleDocMetaOutput,
)


class IngestStageMetagenStepAssembleDocMeta(IngestStageMetagenStepBase):
    """
    Assemble the merged ``doc_meta`` and the metagen result record.

    Reads the two scope outputs + the budget-gate estimate + the IR/implicit/user inputs; writes the
    chunks, the doc_fields, the merged doc_meta, and the metagen result.
    """

    SPEC = NodeSpec(
        key="assemble_doc_meta",
        name="Assemble doc meta",
        description="Merge implicit + IR system fields + generated + user into doc_meta.",
    )
    Input = IngestStageMetagenStepAssembleDocMetaInput
    Output = IngestStageMetagenStepAssembleDocMetaOutput
    Context = IngestStageMetagenStepAssembleDocMetaContext
    Error = IngestStageMetagenStepAssembleDocMetaError

    async def execute(
        self, ctx: IngestStageMetagenStepAssembleDocMetaContext
    ) -> IngestStageMetagenStepAssembleDocMetaOutput:
        """
        Merge the document-level metadata and fold the scope outputs into the result.

        Args:
            ctx (IngestStageMetagenStepAssembleDocMetaContext): Typed input (scopes + IR + meta).

        Returns:
            IngestStageMetagenStepAssembleDocMetaOutput: chunks + doc_fields + doc_meta + result.
        """
        # 1. Assemble doc_meta with the legacy precedence (later wins).
        data = ctx.input
        doc_meta = self._assemble_doc_meta(data)

        # 2. Fold the two scope outputs + the budget estimate into the metagen result.
        traces = [t for t in (data.chunk_trace, data.doc_trace) if t is not None]
        result = IngestStageMetagenResult(
            chunks=data.chunks,
            doc_fields=data.doc_fields,
            n_generated=data.chunk_n_generated + data.doc_n_generated,
            est_cost_usd=data.est_cost_usd,
            chain_traces=traces,
        )

        self.logger.info(
            f"Metagen assembled: n_generated={result.n_generated} doc_meta_keys={len(doc_meta)} "
            f"est_cost=${result.est_cost_usd:.4f}"
        )
        return IngestStageMetagenStepAssembleDocMetaOutput(
            chunks=data.chunks,
            doc_fields=data.doc_fields,
            doc_meta=doc_meta,
            metagen_result=result,
        )

    def _assemble_doc_meta(
        self, data: IngestStageMetagenStepAssembleDocMetaInput
    ) -> dict[str, Any]:
        """
        Build the document-level metadata fed to the embed/index stage, mirroring legacy s456_runner.

        Precedence (later wins): file-intrinsic implicit_meta + IR-derived system fields, then
        generated ``doc_fields`` (document scope), then user-supplied ``doc_user_meta`` — so a user
        value always overrides a generated one, which overrides an implicit one.

        Args:
            data (IngestStageMetagenStepAssembleDocMetaInput): The resolved step input.

        Returns:
            dict[str, Any]: The assembled document-level metadata.
        """
        ir = data.ir
        return {
            **(data.implicit_meta or {}),
            "language": ir.language,
            "page_count": ir.n_pages,
            "n_blocks": len(ir.blocks),
            "n_figures": len(ir.figure_blocks),
            "n_tables": len(ir.table_blocks),
            **(data.doc_fields or {}),
            **(data.doc_user_meta or {}),
        }


__all__ = ["IngestStageMetagenStepAssembleDocMeta"]
