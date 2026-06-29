# ====== Code Summary ======
# Unit tests for the S2 enrich `chart_to_data` gate.  They assert that the structured
# chart-to-data extraction (the data_table + the chart_extractions counter) runs IFF
# enrich.chart_to_data is True — a CHART figure with the flag off is enriched like a normal
# figure (VLM description only).  The VLM provider + provider-call cache are mocked.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import FigureKind
from common_libs.pipeline.bricks.chain import Chain
from common_libs.pipeline.bricks.chain.gate import ChainGate, ChainGateConfig
from common_libs.providers.results.vlm_result import VlmResult
from common_libs.pipeline.stages.s2_enrich.figure_routing import FigureRoutingHelpers
from common_libs.pipeline.stages.s2_enrich.models import S2Counters


class _FakeVlmProvider:
    """Test double VLM provider whose describe() returns a structured chart table."""

    name = "fake_vlm"
    version = "test"

    async def describe(
        self,
        crop_bytes: bytes,
        grounding: str | None = None,
        schema: Any = None,
    ) -> VlmResult:
        """Always return a structured table; chart-to-data gating lives in maybe_vlm."""
        _ = (crop_bytes, grounding, schema)
        return VlmResult(
            description="a bar chart of revenue per quarter",
            structured={"table": [["Q1", "10"], ["Q2", "20"]]},
            quality=1.0,
        )


def _vlm_chain(provider: _FakeVlmProvider) -> Chain[Any, Any]:
    """Build a single-provider VLM chain with a permissive gate."""
    return Chain(
        stage="vlm",
        providers=[provider],
        gate=ChainGate(ChainGateConfig(min_score=0.0)),
    )


def _cache_miss() -> AsyncMock:
    """Provider-call cache that always misses (get→None) and accepts puts."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.put = AsyncMock(return_value=None)
    return cache


@pytest.mark.asyncio
async def test_chart_to_data_enabled_extracts_table() -> None:
    """With chart_to_data=True, a CHART yields a data_table and increments the counter."""
    # 1. Arrange a CHART figure, a fake VLM, and a missing cache.
    provider = _FakeVlmProvider()
    counters = S2Counters()

    # 2. Run the VLM routing with the flag ON.
    description, data_table = await FigureRoutingHelpers.maybe_vlm(
        vlm_chain=_vlm_chain(provider),
        provider_cache=_cache_miss(),
        kind=FigureKind.CHART,
        crop_bytes=b"png-bytes",
        crop_hash="deadbeef",
        ocr_text=None,
        chart_to_data=True,
        block_traces=[],
        counters=counters,
    )

    # 3. The structured extraction ran: a table came back and the counter ticked.
    #    maybe_vlm gates data_table extraction on `use_chart_schema = CHART and chart_to_data`.
    assert description == "a bar chart of revenue per quarter"
    assert data_table == [["Q1", "10"], ["Q2", "20"]]
    assert counters.chart_extractions == 1


@pytest.mark.asyncio
async def test_chart_to_data_disabled_skips_table() -> None:
    """With chart_to_data=False, a CHART is described but no data_table is extracted."""
    # 1. Arrange the same CHART figure, but with the flag OFF.
    provider = _FakeVlmProvider()
    counters = S2Counters()

    # 2. Run the VLM routing with the flag OFF.
    description, data_table = await FigureRoutingHelpers.maybe_vlm(
        vlm_chain=_vlm_chain(provider),
        provider_cache=_cache_miss(),
        kind=FigureKind.CHART,
        crop_bytes=b"png-bytes",
        crop_hash="deadbeef",
        ocr_text=None,
        chart_to_data=False,
        block_traces=[],
        counters=counters,
    )

    # 3. VLM description still produced, but the structured extraction was skipped:
    #    the CHART was treated as a normal figure (VLM description only).
    assert description == "a bar chart of revenue per quarter"
    assert data_table is None
    assert counters.chart_extractions == 0
