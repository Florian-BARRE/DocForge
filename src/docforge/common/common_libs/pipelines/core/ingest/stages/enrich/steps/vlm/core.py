# ====== Code Summary ======
# IngestStageEnrichStepVlm - the VLM enrich capability pass. It runs the VLM chain (provider-call
# cached on the crop sha256 + grounding/chart-schema params) over EXACTLY the figures the classify
# step's routing marked ``do_vlm``, in document order, grounding each call on the OCR text recorded by
# the OCR step. It records the VLM description + the raw structured output (which the chart step later
# mines for a data table) + the VLM trace on each FigureWork. The chart-to-data decision
# (``use_chart_schema``) was taken at classify time and is a PARAMETER of THIS single VLM call - never
# a second provider call - so the cache key matches the legacy path exactly.

# ====== Internal Project Imports ======
from common_libs.pipelines import ChainRef, NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ...vlm_runner import VlmRunner
from ..base import IngestStageEnrichStepBase
from .context import IngestStageEnrichStepVlmContext
from .errors import IngestStageEnrichStepVlmError
from .io import IngestStageEnrichStepVlmInput, IngestStageEnrichStepVlmOutput


class IngestStageEnrichStepVlm(IngestStageEnrichStepBase):
    """
    VLM-describe the figures the routing marked for a visual description.

    Reads the work list; folds each routed figure's description + raw structured output into its
    FigureWork (grounded on the OCR text) and re-emits the work list (with the VLM counters).
    """

    SPEC = NodeSpec(
        key="vlm",
        name="VLM",
        description=(
            "Describe the figures the routing selected via a vision-language model, grounded on the "
            "OCR text."
        ),
    )
    Input = IngestStageEnrichStepVlmInput
    Output = IngestStageEnrichStepVlmOutput
    Context = IngestStageEnrichStepVlmContext
    Error = IngestStageEnrichStepVlmError
    REQUIRES = (
        ChainRef(name="vlm_chain", category="vlm", description="Ordered VLM chain (empty when disabled)."),
        ServiceRef(name="provider_cache", description="Cross-document provider-call cache."),
    )

    async def execute(
        self, ctx: IngestStageEnrichStepVlmContext
    ) -> IngestStageEnrichStepVlmOutput:
        """
        Run the VLM over the routed figures and fold the descriptions into the work list.

        Args:
            ctx (IngestStageEnrichStepVlmContext): Typed input + VLM chain + provider cache.

        Returns:
            IngestStageEnrichStepVlmOutput: The threaded work list + VLM counters.
        """
        works = ctx.input.figure_works

        # 1. VLM only the figures the routing marked, in document (insertion) order; ground each call
        # on the figure's OCR text and request the chart schema iff the routing decided so.
        calls = hits = 0
        for work in works:
            if not work.do_vlm:
                continue
            vlm_result, vlm_trace, was_hit = await VlmRunner.run_vlm(
                ctx.vlm_chain, ctx.provider_cache, work.crop_bytes, work.crop_hash,
                work.ocr_text, work.use_chart_schema,
            )
            work.vlm_trace = vlm_trace
            if vlm_result is None:
                continue
            work.description = vlm_result.description or None
            work.vlm_structured = vlm_result.structured
            hits, calls = (hits + 1, calls) if was_hit else (hits, calls + 1)

        self.logger.info(f"Enrich VLM done: vlm(call/hit)={calls}/{hits}")
        return IngestStageEnrichStepVlmOutput(
            figure_works=works, vlm_calls=calls, vlm_cache_hits=hits
        )


__all__ = ["IngestStageEnrichStepVlm"]
