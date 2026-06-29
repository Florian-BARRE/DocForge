# ====== Code Summary ======
# EnrichResult — the ``enrich_result`` output contract of the enrich stage. Carries the enriched IR
# plus all per-run accounting counters (chain call / cache-hit counts). Field names are kept
# byte-identical to the legacy S2Result/EnrichResult so the worker node-cache codec round-trip stays
# unchanged. Kept in its own module so it can be imported without pulling in the stage's chains.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR


@dataclass(slots=True)
class EnrichResult:
    """
    Output of the enrich stage (the enriched IR + per-run counts).

    Attributes:
        ir (DocumentIR): The IR with all FIGURE blocks enriched in-place.
        figures_processed (int): FIGURE blocks that completed the full routing.
        ocr_calls (int): OCR chain invocations (cache misses only).
        vlm_calls (int): VLM chain invocations (cache misses only).
        chart_extractions (int): Charts where structured table data was extracted.
        ocr_cache_hits (int): OCR results served from the provider-call cache.
        vlm_cache_hits (int): VLM results served from the provider-call cache.
        classifier_calls (int): Classifier chain invocations (cache misses only).
        classifier_cache_hits (int): Classifier results served from cache.
    """

    ir: DocumentIR
    figures_processed: int = 0
    ocr_calls: int = 0
    vlm_calls: int = 0
    chart_extractions: int = 0
    # Hits = a duplicate crop answered from ProviderCallCache without invoking the chain (zero
    # latency). Misses = the chain ran. ocr_calls / vlm_calls remain the miss counts.
    ocr_cache_hits: int = 0
    vlm_cache_hits: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0


__all__ = ["EnrichResult"]
