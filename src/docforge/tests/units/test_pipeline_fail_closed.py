# ====== Code Summary ======
# Fail-closed robustness tests for the embed chain + provider contracts (the parts that live
# below the engine). The engine/lifecycle fail-closed guarantees (mark_failed on stage error,
# collection_id gate, missing-original) moved to the dynamic engine and are covered by
# test_dynamic_engine.py + test_dynamic_worker_hooks.py. This file keeps:
#   1. S6Embedder raises (or degrades, alignment-preserving) when the embed chain is exhausted.
#   2. PaddleOcr / LayoutLabels / classifier-chain providers re-raise on engine failure (no masked
#      degraded result), so the provider chain records the failure and escalates / exhausts.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.pipeline.bricks.chain import Chain, ChainExhaustedError
from common_libs.pipeline.bricks.chain.gate import ChainGate, ChainGateConfig
from common_libs.pipeline.stages.s6_embed_index.embedder import S6Embedder


# ─── Embed provider doubles ──────────────────────────────────────────────────


class _AlwaysRaisingEmbedProvider:
    """Embed provider whose every call raises — exhausts the chain."""

    name = "boom_embed"
    version = "test"
    dimension = 8

    async def embed(self, texts: list[str]) -> Any:
        raise RuntimeError("embed backend unreachable (simulated ReadTimeout)")


class _MiddleBatchFailingEmbedProvider:
    """Embed provider that raises ONLY for one designated text — to fail a middle batch.

    Produces a deterministic dense vector ``[float(ord(text[0]))] * dimension`` per text so a
    test can assert the surviving batches kept their correct, positionally-aligned vectors.
    """

    name = "middle_fail_embed"
    version = "test"
    dimension = 2

    def __init__(self, fail_text: str) -> None:
        self._fail_text = fail_text

    async def embed(self, texts: list[str]) -> Any:
        from common_libs.providers.results.embed_result import EmbedResult

        if self._fail_text in texts:
            raise RuntimeError(f"simulated failure on batch containing {self._fail_text!r}")
        return EmbedResult(
            vectors=[[float(ord(t[0]))] * self.dimension for t in texts],
            model="test-embed",
        )


# ─── 1. S6Embedder raises / degrades on chain exhaustion ─────────────────────


@pytest.mark.asyncio
async def test_s6_embedder_raises_when_chain_exhausted() -> None:
    """An exhausted embed chain (default failure_policy=raise) must raise ChainExhaustedError."""
    chain: Chain[Any, Any] = Chain(
        stage="embed",
        providers=[_AlwaysRaisingEmbedProvider()],
        gate=ChainGate(ChainGateConfig(min_score=0.6, failure_policy="raise")),
    )
    embedder = S6Embedder(chain, embed_batch_size=16)
    embedder.begin_run()

    with pytest.raises(ChainExhaustedError, match="'embed' chain exhausted"):
        await embedder.embed_texts(["hello world"])


@pytest.mark.asyncio
async def test_s6_embedder_degrades_when_chain_continue() -> None:
    """An exhausted embed chain under failure_policy=continue contributes no vectors (no raise)."""
    chain: Chain[Any, Any] = Chain(
        stage="embed",
        providers=[_AlwaysRaisingEmbedProvider()],
        gate=ChainGate(ChainGateConfig(min_score=0.6, failure_policy="continue")),
    )
    embedder = S6Embedder(chain, embed_batch_size=16)
    embedder.begin_run()

    dense, sparse = await embedder.embed_texts(["hello world"])

    assert dense == [None]  # same-length placeholder, NOT dropped
    assert sparse is None
    assert len(embedder.batch_traces) == 1
    assert embedder.batch_traces[0].final_provider is None
    assert embedder.batch_traces[0].degraded is True


@pytest.mark.asyncio
async def test_s6_embedder_preserves_alignment_when_middle_batch_degrades() -> None:
    """A degraded MIDDLE batch must emit None placeholders so positional alignment is preserved.

    Regression guard: dropping a degraded batch would shift every later text onto the wrong
    vector (silent corruption) and make embed_values raise IndexError. With batch_size=1 and
    the 2nd of three texts failing, the result must be [vec0, None, vec2] — index-aligned.
    """
    chain: Chain[Any, Any] = Chain(
        stage="embed",
        providers=[_MiddleBatchFailingEmbedProvider(fail_text="beta")],
        gate=ChainGate(ChainGateConfig(min_score=0.0, failure_policy="continue")),
    )
    embedder = S6Embedder(chain, embed_batch_size=1)
    embedder.begin_run()

    dense, _sparse = await embedder.embed_texts(["alpha", "beta", "gamma"])

    assert len(dense) == 3
    assert dense[0] == [float(ord("a"))] * 2  # "alpha"
    assert dense[2] == [float(ord("g"))] * 2  # "gamma"
    assert dense[1] is None
    assert len(embedder.batch_traces) == 3
    assert [t.degraded for t in embedder.batch_traces] == [False, True, False]


@pytest.mark.asyncio
async def test_s6_embed_values_no_index_error_when_batch_degrades() -> None:
    """embed_values must scatter None for a degraded batch (no IndexError, alignment kept)."""
    chain: Chain[Any, Any] = Chain(
        stage="embed",
        providers=[_MiddleBatchFailingEmbedProvider(fail_text="beta")],
        gate=ChainGate(ChainGateConfig(min_score=0.0, failure_policy="continue")),
    )
    embedder = S6Embedder(chain, embed_batch_size=1)
    embedder.begin_run()

    dense_out, _sparse_out = await embedder.embed_values(["alpha", None, "gamma", "beta"])

    assert len(dense_out) == 4
    assert dense_out[0] == [float(ord("a"))] * 2  # "alpha" embedded
    assert dense_out[1] is None                   # no value → skipped
    assert dense_out[2] == [float(ord("g"))] * 2  # "gamma" embedded
    assert dense_out[3] is None                   # "beta" batch degraded → None (no IndexError)


# ─── 2. Providers re-raise on engine failure (chain escalation) ──────────────


@pytest.mark.asyncio
async def test_paddle_ocr_reraises_on_engine_failure() -> None:
    """PaddleOCR must raise (not return empty) on engine failure so the chain escalates."""
    from common_libs.pipeline.bricks.providers.ocr.paddle.provider import PaddleOcrProvider
    from common_libs.providers.results.ocr_result import OcrHint

    provider = PaddleOcrProvider()
    with pytest.raises(Exception):
        await provider.extract(b"not-an-image", OcrHint(language="en"))


@pytest.mark.asyncio
async def test_layout_labels_reraises_on_analysis_failure() -> None:
    """LayoutLabels must raise on a true pixel-analysis failure (unreadable image)."""
    from common_libs.pipeline.bricks.providers.classifier.layout_labels.provider import (
        LayoutLabelsClassifier,
    )

    provider = LayoutLabelsClassifier()
    with pytest.raises(Exception):
        await provider.classify(b"not-an-image")


@pytest.mark.asyncio
async def test_failing_classifier_chain_escalates_then_exhausts() -> None:
    """A classifier that raises is a failed attempt; an all-raising chain returns None."""

    class _RaisingClassifier:
        name = "raises"
        version = "test"

        async def classify(self, img_bytes: bytes) -> Any:
            raise RuntimeError("inference crashed")

    chain: Chain[Any, Any] = Chain(
        stage="classifier",
        providers=[_RaisingClassifier(), _RaisingClassifier()],
        gate=ChainGate(ChainGateConfig(min_score=0.5, failure_policy="continue")),
    )
    outcome = await chain.call(lambda p: p.classify(b"x"))

    assert outcome.result is None
    assert outcome.degraded is True
    assert outcome.final_provider is None
    assert len(outcome.attempts) == 2
    assert all(not a.succeeded and a.error for a in outcome.attempts)
