# ====== Code Summary ======
# MetagenAssembleDocMeta — the final metagen node. As the node that holds every document-level input,
# it assembles the merged ``doc_meta`` so the IO graph is closed (the embed/index stage consumes
# doc_meta). The merge precedence is: IR-derived system fields < generated doc_fields < user
# doc_user_meta — a user value always wins over a generated one, which wins over a system one. It also
# folds the two scope outputs (counts + traces) and the budget-gate estimate into the metagen result.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain import ChainTrace, Chunk, DocumentIR
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)

# ====== Local Project Imports ======
from ..result import MetagenResult


class MetagenAssembleDocMetaInput(NodeInput):
    """
    Input of the assemble-doc-meta node.

    Attributes:
        chunks (list[Chunk]): The chunk-scope chunks (with derived_meta filled).
        chunk_n_generated (int): Count of chunk-scope generated values.
        chunk_trace (ChainTrace | None): The chunk-scope chain trace, if any.
        doc_fields (dict): The document-scope generated values.
        doc_n_generated (int): Count of document-scope generated values.
        doc_trace (ChainTrace | None): The document-scope chain trace, if any.
        est_cost_usd (float): The budget-gate cost estimate.
        ir (DocumentIR): The enriched IR (system-field source for doc_meta).
        doc_user_meta (dict | None): Caller-supplied metadata (highest precedence in doc_meta).
    """

    chunks: Annotated[list[Chunk], FromNode("chunk_scope", "chunks")]
    chunk_n_generated: Annotated[int, FromNode("chunk_scope", "n_generated")]
    chunk_trace: Annotated[ChainTrace | None, FromNode("chunk_scope", "chain_trace")]
    doc_fields: Annotated[dict, FromNode("doc_scope", "doc_fields")]
    doc_n_generated: Annotated[int, FromNode("doc_scope", "n_generated")]
    doc_trace: Annotated[ChainTrace | None, FromNode("doc_scope", "chain_trace")]
    est_cost_usd: Annotated[float, FromNode("budget_gate", "est_cost_usd")]
    ir: Annotated[DocumentIR, FromGroupInput()]
    doc_user_meta: Annotated[dict | None, FromGroupInput()]


class MetagenAssembleDocMetaOutput(NodeOutput):
    """
    Output of the assemble-doc-meta node — the stage's downstream artefacts.

    Attributes:
        chunks (list[Chunk]): The same chunks (with chunk-scope derived_meta filled).
        doc_fields (dict): The document-scope generated values.
        doc_meta (dict): The merged document-level metadata (system < generated < user).
        metagen_result (MetagenResult): Counts, estimated cost, and chain traces.
    """

    chunks: list[Chunk]
    doc_fields: dict
    doc_meta: dict
    metagen_result: MetagenResult


class MetagenAssembleDocMeta(ActionNode):
    """
    Assemble the merged ``doc_meta`` and the metagen result record.

    Reads the two scope outputs + the budget-gate estimate + the IR / user inputs; writes the chunks,
    the doc_fields, the merged doc_meta, and the metagen result.
    """

    Input = MetagenAssembleDocMetaInput
    Output = MetagenAssembleDocMetaOutput

    async def execute(self, ctx: Context) -> MetagenAssembleDocMetaOutput:
        """
        Merge the document-level metadata and fold the scope outputs into the result.

        Args:
            ctx (Context): The resolved input (scopes + IR + user meta).

        Returns:
            MetagenAssembleDocMetaOutput: chunks + doc_fields + doc_meta + result.
        """
        # 1. Assemble doc_meta with the precedence (later wins).
        data = ctx.input
        doc_meta = self._assemble_doc_meta(data)

        # 2. Fold the two scope outputs + the budget estimate into the metagen result.
        traces = [t for t in (data.chunk_trace, data.doc_trace) if t is not None]
        result = MetagenResult(
            chunks=data.chunks,
            doc_fields=data.doc_fields,
            n_generated=data.chunk_n_generated + data.doc_n_generated,
            est_cost_usd=data.est_cost_usd,
            chain_traces=traces,
        )

        # Only the productive path (something was generated) is a key lifecycle event; the no-op run
        # (metagen disabled / no targets => n_generated == 0) is traced at debug so it does not spam.
        summary = (
            f"Metagen assembled: n_generated={result.n_generated} doc_meta_keys={len(doc_meta)} "
            f"est_cost=${result.est_cost_usd:.4f}"
        )
        if result.n_generated > 0:
            self.logger.info(summary)
        else:
            self.logger.debug(summary)
        return MetagenAssembleDocMetaOutput(
            chunks=data.chunks,
            doc_fields=data.doc_fields,
            doc_meta=doc_meta,
            metagen_result=result,
        )

    def _assemble_doc_meta(self, data: MetagenAssembleDocMetaInput) -> dict[str, Any]:
        """
        Build the document-level metadata fed to the embed/index stage.

        Precedence (later wins): IR-derived system fields, then generated ``doc_fields`` (document
        scope), then user-supplied ``doc_user_meta`` — so a user value always overrides a generated
        one, which overrides a system one.

        Args:
            data (MetagenAssembleDocMetaInput): The resolved node input.

        Returns:
            dict[str, Any]: The assembled document-level metadata.
        """
        ir = data.ir
        return {
            "language": ir.language,
            "page_count": ir.n_pages,
            "n_blocks": len(ir.blocks),
            "n_figures": len(ir.figure_blocks),
            "n_tables": len(ir.table_blocks),
            **(data.doc_fields or {}),
            **(data.doc_user_meta or {}),
        }


__all__ = [
    "MetagenAssembleDocMeta",
    "MetagenAssembleDocMetaInput",
    "MetagenAssembleDocMetaOutput",
]
