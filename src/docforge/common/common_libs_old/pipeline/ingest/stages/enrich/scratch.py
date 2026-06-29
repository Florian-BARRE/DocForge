# ====== Code Summary ======
# EnrichScratch + FigureWork — the in-flight hand-off carried between the enrich stage's per-capability
# steps. Where the legacy FigureEnricher processed ONE figure end-to-end (classify -> OCR -> VLM ->
# chart) before moving to the next, the native enrich stage runs ONE capability over ALL figures per
# step. The routing DECISION (taken once, at classify time) and the per-figure intermediate artefacts
# (crop bytes/hash, kind, OCR text, VLM description + raw structured output, data table, accumulated
# chain traces) therefore have to outlive a single step: they live on a FigureWork per enrichable
# figure, collected in an EnrichScratch stashed under ``ctx.aux[ENRICH_SCRATCH_KEY]`` (same ctx.aux
# pattern as the ingest/embed_index stages). Iterating the scratch in insertion order reproduces the
# legacy per-figure document order, so the provider-call cache hit/miss pattern is byte-identical.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainTrace, FigureEnrichment, FigureKind

# ====== Local Project Imports ======
from .result import EnrichCounters

# Context aux key under which the enrich steps share their in-flight scratch.
ENRICH_SCRATCH_KEY = "enrich_scratch"


@dataclass
class FigureWork:
    """
    Mutable per-figure working state threaded across the enrich stage's per-capability steps.

    Seeded by the classify step (identity + crop + classification + routing decision + the classify
    trace), then filled by the OCR / VLM / chart steps for the figures the routing marked. The IR
    writer reads :meth:`enrichment` + :meth:`traces` to rebuild each FIGURE block.

    Attributes:
        block_id (str): IR block id this work item enriches.
        crop_key (str): Object-store key of the figure crop (carried onto the enrichment).
        crop_bytes (bytes): Downloaded crop image bytes (shared by every capability call).
        crop_hash (str): SHA-256 hex digest of ``crop_bytes`` (the provider-call cache content key).
        kind (FigureKind): Classified figure kind (drives the routing decision).
        relevance (float): Classifier confidence carried onto the enrichment.
        decorative (bool): True when the figure was gated as DECORATIVE (no OCR/VLM/chart).
        do_ocr (bool): Routing decision — run the OCR capability over this figure.
        do_vlm (bool): Routing decision — run the VLM capability over this figure.
        use_chart_schema (bool): Routing decision — request structured chart-to-data from the VLM.
        base_traces (list[ChainTrace]): The block's pre-enrich chain traces (preserved verbatim).
        classify_trace (ChainTrace | None): The classify capability trace.
        ocr_trace (ChainTrace | None): The OCR capability trace (only when ``do_ocr``).
        vlm_trace (ChainTrace | None): The VLM capability trace (only when ``do_vlm``).
        ocr_text (str | None): Text extracted by OCR (grounding for the VLM + the enrichment).
        description (str | None): VLM caption for the enrichment.
        vlm_structured (dict | None): Raw VLM structured output (the chart step extracts its table).
        data_table (list[list[str]] | None): Structured chart-to-data table for the enrichment.
    """

    block_id: str
    crop_key: str
    crop_bytes: bytes
    crop_hash: str
    kind: FigureKind
    relevance: float
    decorative: bool
    do_ocr: bool
    do_vlm: bool
    use_chart_schema: bool
    base_traces: list[ChainTrace] = field(default_factory=list)
    classify_trace: ChainTrace | None = None
    ocr_trace: ChainTrace | None = None
    vlm_trace: ChainTrace | None = None
    ocr_text: str | None = None
    description: str | None = None
    vlm_structured: dict | None = None
    data_table: list[list[str]] | None = None

    def traces(self) -> list[ChainTrace]:
        """
        Assemble this figure's chain traces in the legacy append order.

        The order reproduces ``FigureEnricher.process_block`` exactly: the pre-enrich traces, then
        the classify trace, then (when routed) the OCR trace, then (when routed) the VLM trace.

        Returns:
            list[ChainTrace]: The block's full trace list after enrichment.
        """
        # 1. Start from the pre-enrich traces (parser lineage etc.), then append in capability order.
        out: list[ChainTrace] = list(self.base_traces)
        if self.classify_trace is not None:
            out.append(self.classify_trace)
        if self.ocr_trace is not None:
            out.append(self.ocr_trace)
        if self.vlm_trace is not None:
            out.append(self.vlm_trace)
        return out

    def enrichment(self) -> FigureEnrichment:
        """
        Build the FigureEnrichment from the current (possibly partial) work state.

        Decorative figures carry only kind/crop_key/relevance (no OCR/VLM/chart), exactly as the
        legacy gate produced. Other figures carry whatever the capability steps have filled so far.

        Returns:
            FigureEnrichment: The enrichment slot for this figure block.
        """
        if self.decorative:
            return FigureEnrichment(kind=self.kind, crop_key=self.crop_key, relevance=self.relevance)
        return FigureEnrichment(
            kind=self.kind,
            crop_key=self.crop_key,
            relevance=self.relevance,
            ocr_text=self.ocr_text,
            description=self.description,
            data_table=self.data_table,
        )


@dataclass
class EnrichScratch:
    """
    Cross-step accumulator for the enrich stage's per-capability passes.

    Holds the ordered figure work items (insertion order == document order) plus the run-level
    counter accumulator. The classify step populates ``figures``; the OCR / VLM / chart steps mutate
    the matching work items; every step ticks ``counters`` and re-applies the scratch onto the IR.

    Attributes:
        language (str): Document language hint passed to the OCR capability.
        figures (dict[str, FigureWork]): Enrichable figures keyed by block id, in document order.
        counters (EnrichCounters): Run-level accounting accumulator.
    """

    language: str
    figures: dict[str, FigureWork] = field(default_factory=dict)
    counters: EnrichCounters = field(default_factory=EnrichCounters)


__all__ = ["EnrichScratch", "FigureWork", "ENRICH_SCRATCH_KEY"]
