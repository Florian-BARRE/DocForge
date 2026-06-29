# ====== Code Summary ======
# FigureRoutingHelpers — static OCR and VLM routing steps for a single figure.  Each helper
# runs its capability through CacheRunner when the figure kind warrants it, appends the
# resulting ChainTrace, mutates the shared S2Counters, and returns the extracted text /
# description (+ chart table).  Extracted from FigureEnricher to keep process_block focused.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from common_libs.pipeline.bricks.chain import Chain

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainTrace, FigureKind
from common_libs.pipeline.caches.provider_cache import ProviderCallCache

# ====== Local Project Imports ======
from .cache_runner import CacheRunner
from .models import S2Counters

# Figure kinds that trigger OCR routing.
_OCR_KINDS: frozenset[FigureKind] = frozenset(
    {FigureKind.SCANNED_TEXT, FigureKind.CHART, FigureKind.DIAGRAM}
)
# Figure kinds that trigger VLM routing.
_VLM_KINDS: frozenset[FigureKind] = frozenset(
    {FigureKind.CHART, FigureKind.DIAGRAM, FigureKind.PHOTO}
)


class FigureRoutingHelpers:
    """
    Static OCR / VLM routing steps for a single figure block.

    Both helpers no-op (returning empty values) when the chain is absent or the figure kind
    does not warrant the capability.  They append the produced trace to ``block_traces`` and
    update ``counters`` in place.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("FigureRoutingHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    async def maybe_ocr(
        ocr_chain: Chain[Any, Any] | None,
        provider_cache: ProviderCallCache,
        kind: FigureKind,
        crop_bytes: bytes,
        crop_hash: str,
        doc_language: str,
        block_traces: list[ChainTrace],
        counters: S2Counters,
    ) -> str | None:
        """Run OCR if the kind implies text; append the trace and update counters."""
        if not (ocr_chain and kind in _OCR_KINDS):
            return None
        ocr_result, ocr_trace, ocr_was_cache_hit = await CacheRunner.run_ocr(
            ocr_chain, provider_cache, crop_bytes, crop_hash, doc_language,
        )
        block_traces.append(ocr_trace)
        if ocr_result is None:
            return None
        ocr_text = ocr_result.text if ocr_result.text.strip() else None
        if ocr_was_cache_hit:
            counters.ocr_cache_hits += 1
        else:
            counters.ocr_calls += 1
        return ocr_text

    @staticmethod
    async def maybe_vlm(
        vlm_chain: Chain[Any, Any] | None,
        provider_cache: ProviderCallCache,
        kind: FigureKind,
        crop_bytes: bytes,
        crop_hash: str,
        ocr_text: str | None,
        chart_to_data: bool,
        block_traces: list[ChainTrace],
        counters: S2Counters,
    ) -> tuple[str | None, list[list[str]] | None]:
        """Run VLM (+ optional chart-to-data) if the kind benefits from a visual description."""
        if not (vlm_chain and kind in _VLM_KINDS):
            return None, None

        # Chart-to-data structured extraction is gated by the enrich.chart_to_data flag:
        # only when enabled does a CHART request the structured schema; otherwise a CHART
        # is treated like any other figure (VLM description only, no data-table extraction).
        use_chart_schema = (kind == FigureKind.CHART) and chart_to_data
        vlm_result, vlm_trace, vlm_was_cache_hit = await CacheRunner.run_vlm(
            vlm_chain, provider_cache, crop_bytes, crop_hash, ocr_text, use_chart_schema,
        )
        block_traces.append(vlm_trace)
        if vlm_result is None:
            return None, None

        description = vlm_result.description or None
        if vlm_was_cache_hit:
            counters.vlm_cache_hits += 1
        else:
            counters.vlm_calls += 1

        # Chart-to-data: extract a structured table from the VLM output.
        data_table: list[list[str]] | None = None
        if use_chart_schema and vlm_result.structured:
            raw_table = vlm_result.structured.get("table")
            if raw_table and isinstance(raw_table, list):
                data_table = [
                    [str(cell) for cell in row]
                    for row in raw_table
                    if isinstance(row, list)
                ]
                if data_table:
                    counters.chart_extractions += 1
        return description, data_table


# ------------------- Public API ------------------- #
__all__ = ["FigureRoutingHelpers"]
