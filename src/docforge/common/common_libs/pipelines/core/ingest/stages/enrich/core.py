# ====== Code Summary ======
# IngestStageEnrich - the enrich stage of the ingest pipeline (StageKey.ENRICH). It assembles its
# four per-capability steps (classify -> ocr -> vlm -> chart; the engine derives that order from
# their input bindings) and aggregates their outputs into the enriched IR + EnrichResult. Each step
# runs ONE capability over ALL figures (typed FigureWork list threaded step->step, never ctx.aux);
# the optional OCR / VLM / chart capabilities are inert pass-throughs when their chain is empty / the
# chart flag is off, keeping every binding STATIC. NODE_CACHED: the whole stage is a Merkle node in
# the cache (the chain signatures are folded into the node fingerprint by the worker's cache hook;
# fingerprint_params surfaces the stage's own cache-busting config).

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageEnrichContext
from .errors import IngestStageEnrichError
from .io import IngestStageEnrichInput, IngestStageEnrichOutput
from .ir_builder import EnrichIRWriter
from .result import EnrichResult
from .steps import (
    IngestStageEnrichStepChart,
    IngestStageEnrichStepClassify,
    IngestStageEnrichStepOcr,
    IngestStageEnrichStepVlm,
)


class IngestStageEnrich(IngestStageBase):
    """
    Enrich stage - classify each figure and route it through OCR / VLM / chart-to-data passes.

    Declares its four per-capability steps; the engine orders + runs them and the stage aggregates
    their outputs into the enriched IR + the EnrichResult counts.
    """

    SPEC = StageSpec(
        key=StageKey.ENRICH,
        name="Enrich",
        description=(
            "Classify each figure and route it through OCR / VLM / chart-to-data passes, enriching "
            "the IR in place."
        ),
        cache_policy=CachePolicy.NODE_CACHED,
    )
    Input = IngestStageEnrichInput
    Output = IngestStageEnrichOutput
    Context = IngestStageEnrichContext
    Error = IngestStageEnrichError

    def __init__(
        self,
        ocr_enabled: bool = False,
        vlm_enabled: bool = False,
        chart_to_data: bool = False,
    ) -> None:
        """
        Build the four enrich steps in declaration order (the engine topo-orders them).

        Args:
            ocr_enabled (bool): Whether an OCR chain is wired (drives the classify routing decision).
            vlm_enabled (bool): Whether a VLM chain is wired (drives the classify routing decision).
            chart_to_data (bool): The ``enrich.chart_to_data`` flag (drives the chart-schema decision).
        """
        super().__init__()
        self._ocr_enabled = ocr_enabled
        self._vlm_enabled = vlm_enabled
        self._chart_to_data = chart_to_data
        self._steps = [
            IngestStageEnrichStepClassify(
                ocr_enabled=ocr_enabled,
                vlm_enabled=vlm_enabled,
                chart_to_data=chart_to_data,
            ),
            IngestStageEnrichStepOcr(),
            IngestStageEnrichStepVlm(),
            IngestStageEnrichStepChart(),
        ]

    @property
    def children(self) -> list:
        """The enrich steps (classify -> ocr -> vlm -> chart)."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageEnrichOutput:
        """
        Combine the four step outputs into the enriched IR + EnrichResult.

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageEnrichOutput: The enriched IR + the per-run counts.
        """
        # 1. Pull each step's typed output by its step key.
        classify = child_outputs["classify"]
        ocr = child_outputs["ocr"]
        vlm = child_outputs["vlm"]
        chart = child_outputs["chart"]

        # 2. Rebuild the IR from the classified IR + the final (fully enriched) work list.
        enriched_ir = EnrichIRWriter.apply(classify.ir, chart.figure_works)

        # 3. Snapshot the per-capability counters into the EnrichResult.
        result = EnrichResult(
            ir=enriched_ir,
            figures_processed=classify.figures_processed,
            classifier_calls=classify.classifier_calls,
            classifier_cache_hits=classify.classifier_cache_hits,
            ocr_calls=ocr.ocr_calls,
            ocr_cache_hits=ocr.ocr_cache_hits,
            vlm_calls=vlm.vlm_calls,
            vlm_cache_hits=vlm.vlm_cache_hits,
            chart_extractions=chart.chart_extractions,
        )
        return IngestStageEnrichOutput(ir=enriched_ir, enrich_result=result)

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the stage's own cache-busting config for the NODE_CACHED node fingerprint.

        The classifier / OCR / VLM chain signatures are folded into the node fingerprint by the
        worker's cache hook (it holds the registry that resolves the chains); this method surfaces the
        stage-level config that also invalidates the enrich node cache when it changes.

        Returns:
            dict[str, Any]: The stage's fingerprint parameter dict.
        """
        # The classifier/OCR/VLM CHAIN SIGNATURES are folded into the NODE_CACHED enrich fingerprint by
        # the worker's EngineHooks cache hook (the chains are run-time injected services, not reachable
        # from this method), so this method surfaces only the cache-busting capability flags.
        return {
            "ocr_enabled": self._ocr_enabled,
            "vlm_enabled": self._vlm_enabled,
            "chart_to_data": self._chart_to_data,
        }


__all__ = ["IngestStageEnrich"]
