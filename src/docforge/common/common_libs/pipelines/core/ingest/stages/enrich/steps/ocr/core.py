# ====== Code Summary ======
# IngestStageEnrichStepOcr - the OCR enrich capability pass. It runs the OCR chain (provider-call
# cached on the crop sha256 + language) over EXACTLY the figures the classify step's routing marked
# ``do_ocr``, in document order, and records the extracted text + the OCR trace on each FigureWork.
# It threads the (mutated) work list onward and surfaces the OCR call / cache-hit counters. When the
# OCR chain is empty (capability disabled), no figure is marked ``do_ocr`` and the step passes the
# work list through unchanged.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ...cache_runner import CacheRunner
from ..base import IngestStageEnrichStepBase
from .context import IngestStageEnrichStepOcrContext
from .errors import IngestStageEnrichStepOcrError
from .io import IngestStageEnrichStepOcrInput, IngestStageEnrichStepOcrOutput


class IngestStageEnrichStepOcr(IngestStageEnrichStepBase):
    """
    OCR the figures the routing marked for text extraction.

    Reads the classified ``ir`` + the work list; folds the extracted text into each routed figure's
    FigureWork and re-emits the work list (with the OCR counters).
    """

    SPEC = NodeSpec(
        key="ocr",
        name="OCR",
        description="Extract text from the text-bearing figures the routing selected.",
    )
    Input = IngestStageEnrichStepOcrInput
    Output = IngestStageEnrichStepOcrOutput
    Context = IngestStageEnrichStepOcrContext
    Error = IngestStageEnrichStepOcrError
    REQUIRES = (
        ServiceRef(name="ocr_chain", description="Ordered OCR chain (empty when disabled)."),
        ServiceRef(name="provider_cache", description="Cross-document provider-call cache."),
    )

    async def execute(
        self, ctx: IngestStageEnrichStepOcrContext
    ) -> IngestStageEnrichStepOcrOutput:
        """
        Run OCR over the routed figures and fold the extracted text into the work list.

        Args:
            ctx (IngestStageEnrichStepOcrContext): Typed input + OCR chain + provider cache.

        Returns:
            IngestStageEnrichStepOcrOutput: The threaded work list + OCR counters.
        """
        works = ctx.input.figure_works
        language = ctx.input.ir.language

        # 1. OCR only the figures the routing marked, in document (insertion) order - preserving the
        # legacy provider-call cache hit/miss pattern across duplicate crops.
        calls = hits = 0
        for work in works:
            if not work.do_ocr:
                continue
            ocr_result, ocr_trace, was_hit = await CacheRunner.run_ocr(
                ctx.ocr_chain, ctx.provider_cache, work.crop_bytes, work.crop_hash, language
            )
            work.ocr_trace = ocr_trace
            if ocr_result is None:
                continue
            work.ocr_text = ocr_result.text if ocr_result.text.strip() else None
            hits, calls = (hits + 1, calls) if was_hit else (hits, calls + 1)

        self.logger.info(f"Enrich OCR done: doc_id={ctx.input.ir.doc_id} ocr(call/hit)={calls}/{hits}")
        return IngestStageEnrichStepOcrOutput(
            figure_works=works, ocr_calls=calls, ocr_cache_hits=hits
        )


__all__ = ["IngestStageEnrichStepOcr"]
