# ====== Code Summary ======
# EnrichResult + EnrichCounters — the output contract of the enrich (S2) stage, relocated from the
# former S2Result/S2Counters with byte-identical fields so the worker node-cache codec round-trip
# stays unchanged. EnrichResult carries the enriched IR plus all per-run accounting counters (call /
# cache-hit counts). EnrichCounters is the mutable accumulator the per-capability steps tick as they
# classify / OCR / VLM / chart-extract; the terminal commit copies its values into the immutable
# EnrichResult. Kept in its own module so it can be imported without pulling in the stage's chains.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.domain.ir.models import DocumentIR


@dataclass(slots=True)
class EnrichResult:
    """
    Output of the enrich (S2) stage (counts + the enriched IR).

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

    ir: "DocumentIR"
    figures_processed: int
    ocr_calls: int
    vlm_calls: int
    chart_extractions: int
    # ─── Cache-aware counters (per-run telemetry, not persisted in the node-cache meta) ──────────
    # Hits = a duplicate crop was answered from ProviderCallCache without invoking the underlying
    # chain (zero latency). Misses = the chain ran. ocr_calls / vlm_calls above remain the miss
    # counts (== number of chain invocations); restoring from cache leaves the hit counters at 0.
    ocr_cache_hits: int = 0
    vlm_cache_hits: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0


@dataclass(slots=True)
class EnrichCounters:
    """
    Mutable per-run accounting accumulator for the enrich (S2) stage.

    Mirrors the counter fields of :class:`EnrichResult` but is mutated in place by the per-capability
    steps (classify / OCR / VLM / chart) as each figure is routed. The terminal commit copies the
    final values into the immutable :class:`EnrichResult`.

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
__all__ = ["EnrichResult", "EnrichCounters"]
