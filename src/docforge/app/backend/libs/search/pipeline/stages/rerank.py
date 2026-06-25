# ====== Code Summary ======
# RerankStage — wraps a RerankProvider to re-score retrieval results with a cross-encoder.
# Re-scores the whole candidate pool and returns it fully sorted by rerank score.
# The engine (not this stage) trims the sorted list to the request top_k — the request
# top_k is the single authoritative final-count, never overridden by config.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.search_config import RerankConfig
from common_libs.providers.rerank.base import RerankProvider
from backend.libs.search.hybrid.models import SearchResult


class RerankStage(LoggerClass):
    """
    Cross-encoder reranking stage.

    Takes the retrieval candidate pool, scores each candidate against the query
    using a cross-encoder (RerankProvider), and returns the WHOLE pool sorted by
    descending rerank score.  Trimming to the final count is the engine's job: the
    request ``top_k`` is the single authoritative final-count and must never be
    overridden here by a config value.

    Each returned result's ``score`` is overwritten with its cross-encoder score so the
    surfaced relevance is consistent with the rerank ordering.

    Attributes:
        _config (RerankConfig): Candidate pool sizing (candidate_k).
        _provider (RerankProvider): Cross-encoder provider instance.
    """

    def __init__(self, config: RerankConfig, provider: RerankProvider) -> None:
        """
        Initialize the rerank stage.

        Args:
            config (RerankConfig): Reranking configuration (candidate_k).
            provider (RerankProvider): Cross-encoder reranking provider.
        """
        LoggerClass.__init__(self)
        self._config = config
        self._provider = provider
        self.logger.debug(f"RerankStage: candidate_k={self._config.candidate_k}")

    async def run(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        """
        Re-score the candidate pool and return it fully sorted by rerank score.

        Each returned result's ``score`` is overwritten with its cross-encoder score so the
        displayed relevance matches the rerank ordering.  The list is NOT trimmed here —
        the engine trims the sorted pool to the request top_k.  If the provider raises,
        logs a warning and returns the original (retrieval-ordered) candidates unchanged.

        Args:
            query (str): The user search query (same query used during retrieval).
            results (list[SearchResult]): Retrieval candidates (pre-sorted by Qdrant RRF).

        Returns:
            list[SearchResult]: All candidates sorted by descending rerank score.
        """
        if not results:
            return results

        # 1. Extract text content for scoring (use raw_text from each chunk)
        texts = [r.raw_text or "" for r in results]

        # 2. Score all candidates with the cross-encoder
        try:
            scores = await self._provider.rerank(query=query, texts=texts)
        except Exception as exc:
            self.logger.warning(f"RerankStage: cross-encoder failed, returning original order — {exc}")
            return results

        self.logger.debug(f"RerankStage: scored {len(scores)} candidates")

        # 3. Pair each result with its rerank score for sorting
        scored = [(score, result) for result, score in zip(results, scores)]

        # 4. Sort by descending rerank score and reflect the score onto each result.
        #    No trim here — the engine returns the request top_k from this sorted pool.
        scored.sort(key=lambda t: t[0], reverse=True)
        reranked: list[SearchResult] = []
        for score, result in scored:
            result.score = float(score)
            reranked.append(result)
        return reranked


