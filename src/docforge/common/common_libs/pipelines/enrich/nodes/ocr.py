# ====== Code Summary ======
# The OCR node - the second action of the enrich stage. It runs the injected OCR chain (an escalation
# over OCR providers, provider-call cached on the crop sha256 + language) over EXACTLY the figures the
# classify node's routing marked ``do_ocr``, in document order, and records the extracted text + the
# OCR trace on each FigureWork. It threads the (mutated) work list onward to the VLM node. When the OCR
# chain service is absent / empty, no figure is marked ``do_ocr`` and the work list passes through
# unchanged - the escalation lives entirely inside the injected chain, never in this node.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines.core.ingest.stages.enrich.cache_runner import CacheRunner
from common_libs.pipelines.core.ingest.stages.enrich.figure_work import FigureWork
from common_libs.pipelines.flow import ActionNode, Context, FromNode, NodeInput, NodeOutput


class EnrichOcrInput(NodeInput):
    """Input of the OCR node - the classified IR (language hint) + the seeded work list."""

    ir: Annotated[DocumentIR, FromNode("classify", "ir")]
    figure_works: Annotated[list[FigureWork], FromNode("classify", "figure_works")]


class EnrichOcrOutput(NodeOutput):
    """Output of the OCR node - the work list with OCR text folded in + the OCR counters."""

    figure_works: list[FigureWork]
    ocr_calls: int = 0
    ocr_cache_hits: int = 0


class EnrichOcr(ActionNode):
    """OCR the figures the routing marked for text extraction, threading the work list onward."""

    Input = EnrichOcrInput
    Output = EnrichOcrOutput

    async def execute(self, ctx: Context) -> EnrichOcrOutput:
        """
        Run OCR over the routed figures and fold the extracted text into the work list.

        Args:
            ctx (Context): The resolved input (IR + work list) + the OCR chain / provider cache.

        Returns:
            EnrichOcrOutput: The threaded work list + the OCR counters.
        """
        # 1. OCR only the figures the routing marked, in document (insertion) order - preserving the
        # legacy provider-call cache hit/miss pattern across duplicate crops.
        works = ctx.input.figure_works
        language = ctx.input.ir.language
        ocr_chain = ctx.service("ocr_chain")
        provider_cache = ctx.service("provider_cache")
        calls = hits = 0
        for work in works:
            if not work.do_ocr:
                continue
            ocr_result, ocr_trace, was_hit = await CacheRunner.run_ocr(
                ocr_chain, provider_cache, work.crop_bytes, work.crop_hash, language
            )
            work.ocr_trace = ocr_trace
            if ocr_result is None:
                continue
            work.ocr_text = ocr_result.text if ocr_result.text.strip() else None
            hits, calls = (hits + 1, calls) if was_hit else (hits, calls + 1)

        self.logger.info(f"Enrich OCR done: doc_id={ctx.input.ir.doc_id} ocr(call/hit)={calls}/{hits}")
        return EnrichOcrOutput(figure_works=works, ocr_calls=calls, ocr_cache_hits=hits)


__all__ = ["EnrichOcr", "EnrichOcrInput", "EnrichOcrOutput"]
