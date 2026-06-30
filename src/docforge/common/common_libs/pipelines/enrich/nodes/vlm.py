# ====== Code Summary ======
# The VLM node - the third action of the enrich stage. It runs the injected VLM chain (an escalation
# over VLM providers, provider-call cached on the crop sha256 + grounding/chart-schema params) over
# EXACTLY the figures the classify node's routing marked ``do_vlm``, in document order, grounding each
# call on the OCR text recorded by the OCR node. It records the VLM description + the raw structured
# output (mined later by the chart node) + the VLM trace on each FigureWork, then threads the work list
# onward. The chart-to-data decision (``use_chart_schema``) is a PARAMETER of this single VLM call -
# never a second provider call - so the cache key matches the legacy path exactly.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.core.ingest.stages.enrich.figure_work import FigureWork
from common_libs.pipelines.core.ingest.stages.enrich.vlm_runner import VlmRunner
from common_libs.pipelines.flow import ActionNode, Context, FromNode, NodeInput, NodeOutput


class EnrichVlmInput(NodeInput):
    """Input of the VLM node - the work list from the OCR node (carries the OCR grounding text)."""

    figure_works: Annotated[list[FigureWork], FromNode("ocr", "figure_works")]


class EnrichVlmOutput(NodeOutput):
    """Output of the VLM node - the work list with descriptions folded in + the VLM counters."""

    figure_works: list[FigureWork]
    vlm_calls: int = 0
    vlm_cache_hits: int = 0


class EnrichVlm(ActionNode):
    """VLM-describe the figures the routing marked, grounded on their OCR text."""

    Input = EnrichVlmInput
    Output = EnrichVlmOutput

    async def execute(self, ctx: Context) -> EnrichVlmOutput:
        """
        Run the VLM over the routed figures and fold the descriptions into the work list.

        Args:
            ctx (Context): The resolved input (the work list) + the VLM chain / provider cache.

        Returns:
            EnrichVlmOutput: The threaded work list + the VLM counters.
        """
        # 1. VLM only the figures the routing marked, in document (insertion) order; ground each call
        # on the figure's OCR text and request the chart schema iff the routing decided so.
        works = ctx.input.figure_works
        vlm_chain = ctx.service("vlm_chain")
        provider_cache = ctx.service("provider_cache")
        calls = hits = 0
        for work in works:
            if not work.do_vlm:
                continue
            vlm_result, vlm_trace, was_hit = await VlmRunner.run_vlm(
                vlm_chain, provider_cache, work.crop_bytes, work.crop_hash,
                work.ocr_text, work.use_chart_schema,
            )
            work.vlm_trace = vlm_trace
            if vlm_result is None:
                continue
            work.description = vlm_result.description or None
            work.vlm_structured = vlm_result.structured
            hits, calls = (hits + 1, calls) if was_hit else (hits, calls + 1)

        self.logger.info(f"Enrich VLM done: vlm(call/hit)={calls}/{hits}")
        return EnrichVlmOutput(figure_works=works, vlm_calls=calls, vlm_cache_hits=hits)


__all__ = ["EnrichVlm", "EnrichVlmInput", "EnrichVlmOutput"]
