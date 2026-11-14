# ====== Code Summary ======
# BgeRerankScorer: scores [query, text] pairs with the loaded FlagReranker. This is the
# batching-engine entry point: the engine builds the full pair list from multiple requests, calls
# ``compute_rerank_scores_flat`` once, then scatters the flat score list back to each request's
# future. The reranker and the device label are read through injected getters so the scorer always
# sees the service's CURRENT state.

# ====== Standard Library Imports ======
import time
from collections.abc import Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class BgeRerankScorer(LoggerClass):
    """Runs the cross-encoder over flat [query, text] pairs and returns normalised scores."""

    def __init__(
        self,
        reranker: Callable[[], Any],
        device: Callable[[], str | None],
    ) -> None:
        """
        Args:
            reranker (Callable): Returns the loaded FlagReranker (raises RuntimeError when it is
                not loaded: service not started, or BGE_LOAD_RERANKER=false).
            device (Callable): Returns the resolved device string, or None before load().
        """
        LoggerClass.__init__(self)
        self._reranker = reranker
        self._device = device

    def compute_rerank_scores_flat(self, pairs: list[list[str]]) -> list[float]:
        """
        Score a flat list of [query, text] pairs and return raw float scores.

        This is the batching-engine entry point: the engine builds the full pair list
        from multiple requests, calls this method once, then scatters the flat score
        list back to each request's future. Scores are sigmoid-normalized to [0, 1].

        Args:
            pairs (list[list[str]]): Each inner list is [query, candidate_text].
                Must be non-empty.

        Returns:
            list[float]: One sigmoid-normalized score per input pair, in input order.
        """
        device = self._device() or "unknown"
        n = len(pairs)
        self.logger.debug(f"compute_rerank_scores_flat: {n} pairs, device={device}")

        # 1. Time the scoring call
        t0 = time.perf_counter()
        scores = self._reranker().compute_score(pairs, normalize=True)
        elapsed = time.perf_counter() - t0

        # 2. Normalise to list — compute_score returns a scalar when n=1
        if not isinstance(scores, list):
            scores = [scores]

        self.logger.debug(
            f"compute_rerank_scores_flat: {n} pairs -> {len(scores)} scores in {elapsed:.3f}s (device={device})"
        )
        return [float(s) for s in scores]
