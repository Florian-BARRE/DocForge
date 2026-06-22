# ====== Code Summary ======
# RerankStage â€” wraps a RerankProvider to re-score retrieval results with a cross-encoder.
# Takes the top candidate_k results, scores them, and returns the top_n highest-scoring ones.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.config.pipeline.stages.search_config import RerankConfig
from libs.providers.rerank.base import RerankProvider
from libs.search.hybrid.models import SearchResult


class RerankStage(LoggerClass):
    """
    Cross-encoder reranking stage.

    Takes a list of retrieval candidates, scores each one against the query using
    a cross-encoder (RerankProvider), and returns the top_n results sorted by
    descending rerank score.

    The rerank score is attached to each SearchResult's metadata dict under the
    key ``"rerank_score"`` for downstream inspection.

    Attributes:
        _config (RerankConfig): Candidate count and top_n settings.
        _provider (RerankProvider): Cross-encoder provider instance.
    """

    def __init__(self, config: RerankConfig, provider: RerankProvider) -> None:
        """
        Initialize the rerank stage.

        Args:
            config (RerankConfig): Reranking configuration (candidate_k, top_n).
            provider (RerankProvider): Cross-encoder reranking provider.
        """
        LoggerClass.__init__(self)
        self._config = config
        self._provider = provider
        self.logger.debug(
            f"RerankStage: candidate_k={self._config.candidate_k} top_n={self._config.top_n}"
        )

    async def run(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        """
        Re-score results with the cross-encoder and return top_n sorted by rerank score.

        Attaches ``rerank_score`` to each result's metadata for downstream use.
        If the provider raises, logs a warning and returns the original results unchanged.

        Args:
            query (str): The user search query (same query used during retrieval).
            results (list[SearchResult]): Retrieval candidates (pre-sorted by Qdrant RRF).

        Returns:
            list[SearchResult]: Top ``top_n`` results sorted by descending rerank score.
        """
        if not results:
            return results

        # 1. Extract text content for scoring (use raw_text from each chunk)
        texts = [r.raw_text or "" for r in results]

        # 2. Score all candidates with the cross-encoder
        try:
            scores = await self._provider.rerank(query=query, texts=texts)
        except Exception as exc:
            self.logger.warning(f"RerankStage: cross-encoder failed, returning original order â€” {exc}")
            return results[: self._config.top_n]

        self.logger.debug(f"RerankStage: scored {len(scores)} candidates")

        # 3. Pair each result with its rerank score for sorting
        scored = [(score, result) for result, score in zip(results, scores)]

        # 4. Sort by descending rerank score and trim to top_n
        scored.sort(key=lambda t: t[0], reverse=True)
        return [r for _, r in scored[: self._config.top_n]]

