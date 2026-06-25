# ====== Code Summary ======
# S2Result dataclass — the output contract of the S2 enrichment stage.
# Carries the enriched IR plus all per-run accounting counters (call/hit counts).

from __future__ import annotations

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from common_libs.domain.ir.models import DocumentIR


@dataclass(slots=True)
class S2Result:
    """
    Output of the S2 enrichment stage (counts + the enriched IR).

    Attributes:
        ir (DocumentIR): The IR with all FIGURE blocks enriched in-place.
        figures_processed (int): Number of FIGURE blocks that completed the full routing.
        ocr_calls (int): Number of OCR chain invocations (cache misses only).
        vlm_calls (int): Number of VLM chain invocations (cache misses only).
        chart_extractions (int): Number of charts where structured table data was extracted.
        ocr_cache_hits (int): Number of OCR results served from the provider-call cache.
        vlm_cache_hits (int): Number of VLM results served from the provider-call cache.
        classifier_calls (int): Number of classifier chain invocations (cache misses only).
        classifier_cache_hits (int): Number of classifier results served from cache.
    """

    ir: DocumentIR
    figures_processed: int
    ocr_calls: int
    vlm_calls: int
    chart_extractions: int
    # ─── Cache-aware counters (Phase A) ─────────────────────────────────────────
    # Hits = a duplicate crop was answered from ProviderCallCache without
    # invoking the underlying chain (zero latency).  Misses
    # = the chain ran.  ocr_calls / vlm_calls above remain the miss counts
    # (== number of chain invocations) for backward compatibility.
    ocr_cache_hits: int = 0
    vlm_cache_hits: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0


@dataclass(slots=True)
class S2Counters:
    """
    Mutable per-run accounting accumulator for the S2 enrichment stage.

    Mirrors the counter fields of :class:`S2Result` but is mutated in place by
    ``FigureEnricher.process_block`` as each figure is routed.  The stage copies the
    final counter values into the immutable ``S2Result`` it returns.

    Attributes:
        figures_processed (int): FIGURE blocks that completed the full routing.
        ocr_calls (int): OCR chain invocations (cache misses only).
        vlm_calls (int): VLM chain invocations (cache misses only).
        chart_extractions (int): Charts where structured table data was extracted.
        ocr_cache_hits (int): OCR results served from the provider-call cache.
        vlm_cache_hits (int): VLM results served from the provider-call cache.
        classifier_calls (int): Classifier chain invocations (cache misses only).
        classifier_cache_hits (int): Classifier results served from cache.
    """

    figures_processed: int = 0
    ocr_calls: int = 0
    vlm_calls: int = 0
    chart_extractions: int = 0
    ocr_cache_hits: int = 0
    vlm_cache_hits: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0


# ------------------- Public API ------------------- #
__all__ = ["S2Result", "S2Counters"]
