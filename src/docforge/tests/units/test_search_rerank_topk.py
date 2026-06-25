# ====== Code Summary ======
# Unit tests for the rerank result-count semantics (FIX 3):
#   - RerankStage re-scores the WHOLE candidate pool and returns it sorted (no trim).
#   - SearchPipelineEngine returns exactly the request top_k from that sorted pool,
#     with the pre-rerank pool sized by candidate_k (clamped up to top_k).
#   - The request top_k is honored identically with rerank on and off.

from unittest.mock import AsyncMock

import pytest

from common_libs.config.pipeline.stages.search_config import SearchConfig
from backend.libs.search.hybrid.models import SearchResult
from backend.libs.search.pipeline.engine import SearchPipelineEngine
from backend.libs.search.pipeline.stages.rerank import RerankStage


def _results(n: int) -> list[SearchResult]:
    """Build n retrieval candidates with descending retrieval scores."""
    return [
        SearchResult(
            chunk_id=f"c{i}", document_id=f"d{i}", score=float(n - i),
            raw_text=f"text {i}", strategy="recursive", token_count=10,
        )
        for i in range(n)
    ]


# ── RerankStage: re-scores the whole pool, no trim ────────────────────────────────


class TestRerankStageNoTrim:
    """The stage returns every candidate sorted by rerank score; the engine owns the trim."""

    @pytest.mark.asyncio
    async def test_returns_full_pool_sorted(self) -> None:
        """20 candidates in → 20 reranked out, sorted by descending cross-encoder score."""
        cfg = SearchConfig.from_dict({"rerank": {"enabled": True, "candidate_k": 20}}).rerank
        provider = AsyncMock()
        # Reverse the relevance order: last candidate gets the highest rerank score.
        provider.rerank = AsyncMock(return_value=[float(i) for i in range(20)])
        stage = RerankStage(config=cfg, provider=provider)

        out = await stage.run(query="q", results=_results(20))

        assert len(out) == 20  # no trim — full pool returned
        assert out[0].chunk_id == "c19"  # highest rerank score first
        assert out[-1].chunk_id == "c0"

    @pytest.mark.asyncio
    async def test_provider_failure_returns_pool_unchanged(self) -> None:
        """On provider error the original (retrieval-ordered) pool is returned untrimmed."""
        cfg = SearchConfig.from_dict({"rerank": {"enabled": True, "candidate_k": 20}}).rerank
        provider = AsyncMock()
        provider.rerank = AsyncMock(side_effect=RuntimeError("boom"))
        stage = RerankStage(config=cfg, provider=provider)

        out = await stage.run(query="q", results=_results(15))

        assert len(out) == 15
        assert [r.chunk_id for r in out] == [f"c{i}" for i in range(15)]


# ── Engine: request top_k is the authoritative final count ────────────────────────


def _make_engine(config: SearchConfig, retrieval: AsyncMock, reranker: AsyncMock | None):
    """Build a SearchPipelineEngine with mocked retrieval + optional reranker."""
    return SearchPipelineEngine(
        config=config,
        embed_provider=AsyncMock(),
        retrieval=retrieval,
        reranker=reranker,
        llm=None,
    )


class TestEngineTopKHonored:
    """The engine returns exactly the request top_k, with and without rerank."""

    @pytest.mark.asyncio
    async def test_top_k_honored_with_rerank_on(self) -> None:
        """candidate_k=20 feeds the reranker; the engine returns exactly top_k=5."""
        config = SearchConfig.from_dict(
            {"rerank": {"enabled": True, "candidate_k": 20, "chain": [{"id": "bge_server"}]}}
        )
        retrieval = AsyncMock()
        # Engine must retrieve the candidate pool (>= candidate_k), not just top_k.
        retrieval.search = AsyncMock(return_value=_results(20))
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[float(i) for i in range(20)])

        engine = _make_engine(config, retrieval, reranker)
        outcome = await engine.run(
            query="q", top_k=5, session=AsyncMock(), collection_name="col",
        )

        # 1. Final count is the request top_k, not candidate_k.
        assert len(outcome.results) == 5
        # 2. The reranker was fed the full candidate pool.
        fed_texts = reranker.rerank.call_args.kwargs["texts"]
        assert len(fed_texts) == 20
        # 3. Pool retrieved was sized to candidate_k.
        assert retrieval.search.call_args.kwargs["top_k"] == 20

    @pytest.mark.asyncio
    async def test_top_k_honored_with_rerank_off(self) -> None:
        """With rerank off the engine returns exactly top_k from the retrieved pool."""
        config = SearchConfig.from_dict({})
        retrieval = AsyncMock()
        retrieval.search = AsyncMock(return_value=_results(12))

        engine = _make_engine(config, retrieval, reranker=None)
        outcome = await engine.run(
            query="q", top_k=5, session=AsyncMock(), collection_name="col",
        )

        assert len(outcome.results) == 5

    @pytest.mark.asyncio
    async def test_candidate_k_smaller_than_top_k_is_clamped(self) -> None:
        """A candidate_k below the request top_k cannot starve the final result set."""
        config = SearchConfig.from_dict(
            {"rerank": {"enabled": True, "candidate_k": 3, "chain": [{"id": "bge_server"}]}}
        )
        retrieval = AsyncMock()
        retrieval.search = AsyncMock(return_value=_results(10))
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[float(i) for i in range(10)])

        engine = _make_engine(config, retrieval, reranker)
        await engine.run(query="q", top_k=10, session=AsyncMock(), collection_name="col")

        # Pool must be clamped up to top_k (10), not the smaller candidate_k (3).
        assert retrieval.search.call_args.kwargs["top_k"] == 10
