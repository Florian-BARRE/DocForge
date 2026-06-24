# ====== Code Summary ======
# RerankStage — wraps a RerankProvider to re-score retrieval results with a cross-encoder.
# Takes the top candidate_k results, scores them, and returns the top_n highest-scoring ones.

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

    Takes a list of retrieval candidates, scores each one against the query using
    a cross-encoder (RerankProvider), and returns the top_n results sorted by
    descending rerank score.

    Each returned result's ``score`` is overwritten with its cross-encoder score so the
    surfaced relevance is consistent with the rerank ordering.

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

        Each returned result's ``score`` is overwritten with its cross-encoder score so the
        displayed relevance matches the rerank ordering.  If the provider raises, logs a
        warning and returns the original (retrieval-ordered) results trimmed to top_n.

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
            self.logger.warning(f"RerankStage: cross-encoder failed, returning original order — {exc}")
            return results[: self._config.top_n]

        self.logger.debug(f"RerankStage: scored {len(scores)} candidates")

        # 3. Pair each result with its rerank score for sorting
        scored = [(score, result) for result, score in zip(results, scores)]

        # 4. Sort by descending rerank score, trim to top_n, and reflect the score
        scored.sort(key=lambda t: t[0], reverse=True)
        top: list[SearchResult] = []
        for score, result in scored[: self._config.top_n]:
            result.score = float(score)
            top.append(result)
        return top


