# ====== Code Summary ======
# MetagenStep — the single native step of the metagen (S5b) stage. It delegates to the existing
# S5bMetagenStage (fill chunk.derived_meta in place + return document-scope doc_fields) and, because
# this is the stage that holds every document-level input, ALSO assembles the final doc_meta so the
# IO graph is closed (S6 CONSUMES doc_meta). The doc_meta merge precedence is preserved exactly from
# the legacy s456_runner: implicit IR/file fields < generated doc_fields < user doc_user_meta —
# a user value always wins over a generated one, which wins over an implicit one.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s5b_metagen.core import S5bMetagenStage


class MetagenStep(IngestStep):
    """
    Native metagen step — generates per-chunk/per-doc metadata and assembles the final doc_meta.

    Reads ``chunks``/``ir``/``ingest_result``/``doc_user_meta``; writes ``metagen_result``, ``chunks``,
    ``doc_fields`` and the merged ``doc_meta``.
    """

    KEY: ClassVar[str] = "metagen"
    NAME: ClassVar[str] = "Metagen"
    DESCRIPTION: ClassVar[str] = (
        "Generate LLM-derived metadata per chunk (derived_meta) and per document (doc_fields) "
        "via the metagen provider chain."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("chunks", "ir", "ingest_result", "doc_user_meta")
    PRODUCES: ClassVar[tuple[str, ...]] = ("metagen_result", "chunks", "doc_fields", "doc_meta")

    def __init__(self, metagen: "S5bMetagenStage") -> None:
        """
        Wire the step around the metagen implementation.

        Args:
            metagen (S5bMetagenStage): The metagen implementation (provider chain).
        """
        IngestStep.__init__(self)
        self._metagen = metagen

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the metagen implementation, then assemble and write the final doc_meta.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Generate per-chunk derived_meta (in place) + document-scope doc_fields.
        result = await self._metagen.run(ctx.chunks, ctx.ir)

        # 2. Write the declared PRODUCES back; the doc-scope values feed the doc_meta merge.
        ctx.metagen_result = result
        ctx.chunks = result.chunks
        ctx.doc_fields = result.doc_fields

        # 3. Close the IO graph: assemble doc_meta for the embed/index stage to consume.
        ctx.doc_meta = self._assemble_doc_meta(ctx, result.doc_fields)

    def _assemble_doc_meta(
        self,
        ctx: "PipelineContext",
        doc_fields: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the document-level metadata fed to S6, mirroring legacy ``s456_runner``.

        Precedence (later wins): S0 file-intrinsic implicit_meta + IR-derived system fields, then
        generated ``doc_fields`` (metagen document scope), then user-supplied ``doc_user_meta`` —
        so a user value always overrides a generated one, which overrides an implicit one.

        Args:
            ctx (PipelineContext): The mutable run accumulator (provides ingest_result, ir, doc_user_meta).
            doc_fields (dict[str, Any]): The document-scope generated values from this stage.

        Returns:
            dict[str, Any]: The assembled document-level metadata.
        """
        ir = ctx.ir
        s0 = ctx.ingest_result
        implicit = (getattr(s0, "implicit_meta", None) or {}) if s0 is not None else {}
        return {
            **implicit,
            "language": ir.language,
            "page_count": ir.n_pages,
            "n_blocks": len(ir.blocks),
            "n_figures": len(ir.figure_blocks),
            "n_tables": len(ir.table_blocks),
            **(doc_fields or {}),
            **(ctx.doc_user_meta or {}),
        }


__all__ = ["MetagenStep"]
