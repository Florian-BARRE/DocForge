# ====== Code Summary ======
# S2Result dataclass — the output contract of the S2 enrichment stage.
# Carries the enriched IR plus all per-run accounting counters (budget, call/hit counts).

from __future__ import annotations

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from libs.core.ir.models import DocumentIR


@dataclass(slots=True)
class S2Result:
    """
    Output of the S2 enrichment stage (counts + the enriched IR).

    Attributes:
        ir (DocumentIR): The IR with all FIGURE blocks enriched in-place.
        budget_spent (float): Total USD spent across OCR and VLM calls in this run.
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
    budget_spent: float
    figures_processed: int
    ocr_calls: int
    vlm_calls: int
    chart_extractions: int
    # ─── Cache-aware counters (Phase A) ─────────────────────────────────────────
    # Hits = a duplicate crop was answered from ProviderCallCache without
    # invoking the underlying chain (zero API cost, zero latency).  Misses
    # = the chain ran.  ocr_calls / vlm_calls above remain the miss counts
    # (== number of chain invocations) for backward compatibility.
    ocr_cache_hits: int = 0
    vlm_cache_hits: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0


# ------------------- Public API ------------------- #
__all__ = ["S2Result"]
