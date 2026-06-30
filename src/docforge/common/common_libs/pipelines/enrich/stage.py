# ====== Code Summary ======
# The enrich stage - a GROUP wiring its four action nodes (classify -> ocr -> vlm -> chart) with
# ``always`` transitions (a sequence). Each node runs ONE capability over ALL figures, threading a
# typed FigureWork list node->node; the OCR / VLM passes are inert when their injected chain is empty.
# The escalation over OCR / VLM providers lives INSIDE the injected chain service, so the stage stays a
# flat sequence. Its typed Output is ASSEMBLED from the classified IR (classify) + the final work list
# (chart) into the single enriched DocumentIR consumed by the chunk stage. Input binds to ``parse.ir``.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines.core.ingest.stages.enrich.ir_builder import EnrichIRWriter
from common_libs.pipelines.flow import (
    FromNode,
    GroupNode,
    NodeInput,
    NodeOutput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import EnrichChart, EnrichClassify, EnrichOcr, EnrichVlm


class EnrichStageInput(NodeInput):
    """The enrich stage input - the parsed IR produced by the parse stage."""

    ir: Annotated[DocumentIR, FromNode("parse", "ir")]


class EnrichStageOutput(NodeOutput):
    """The assembled enrich output - the enriched IR + the per-capability telemetry counters."""

    ir: DocumentIR
    # Enrichment telemetry (folded into the document implicit_meta + the job lineage by the worker).
    figures_processed: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0
    ocr_calls: int = 0
    ocr_cache_hits: int = 0
    vlm_calls: int = 0
    vlm_cache_hits: int = 0
    chart_extractions: int = 0


class EnrichStage(GroupNode):
    """Enrich: classify -> ocr -> vlm -> chart, assembled into the single enriched IR."""

    Input = EnrichStageInput
    Output = EnrichStageOutput

    def __init__(
        self, ocr_enabled: bool = False, vlm_enabled: bool = False, chart_to_data: bool = False
    ) -> None:
        """
        Wire the four enrich nodes as a sequence (``always`` edges).

        Args:
            ocr_enabled (bool): Whether an OCR chain is wired (drives the classify routing decision).
            vlm_enabled (bool): Whether a VLM chain is wired (drives the classify routing decision).
            chart_to_data (bool): The ``enrich.chart_to_data`` flag (drives the chart-schema decision).
        """
        super().__init__(
            "enrich",
            [
                EnrichClassify(
                    "classify",
                    ocr_enabled=ocr_enabled,
                    vlm_enabled=vlm_enabled,
                    chart_to_data=chart_to_data,
                ),
                EnrichOcr("ocr"),
                EnrichVlm("vlm"),
                EnrichChart("chart"),
            ],
            [
                Transition("classify", "ocr"),
                Transition("ocr", "vlm"),
                Transition("vlm", "chart"),
            ],
        )

    def assemble(self, outputs: dict, terminal: NodeOutput) -> EnrichStageOutput:
        """
        Assemble the enriched IR from the classified IR + the final per-figure work list.

        The classify node already rebuilt the IR with each figure classified; applying the final work
        list (after OCR / VLM / chart) onto it materialises every enrichment in one pass.

        Args:
            outputs (dict): The four child outputs by id.
            terminal (NodeOutput): The terminal (chart) output (unused - the stage combines two nodes).

        Returns:
            EnrichStageOutput: The single fully-enriched IR.
        """
        # 1. Materialise the final work list onto the classified IR (one rebuild for the whole stage).
        classify, ocr, vlm, chart = (
            outputs["classify"],
            outputs["ocr"],
            outputs["vlm"],
            outputs["chart"],
        )
        enriched_ir = EnrichIRWriter.apply(classify.ir, chart.figure_works)

        # 2. Fold each capability node's counters into the stage telemetry.
        return EnrichStageOutput(
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


__all__ = ["EnrichStage", "EnrichStageInput", "EnrichStageOutput"]
