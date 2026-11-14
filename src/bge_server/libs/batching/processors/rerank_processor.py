# ====== Code Summary ======
# RerankProcessor: batched cross-encoder rerank path. Flattens every request's (query, text)
# pairs, scores them with BgeModelsService.compute_rerank_scores_flat under rerank_lock (a lock
# independent of embed_lock: the reranker is a separate FlagReranker instance), and scatters
# per-request results. Each request's results are re-indexed 0..n-1 (not global offsets) so the
# TEI contract is honoured -- the DocForge bge_reranker provider expects local indices -- and
# sorted score-descending, matching TEI's own /rerank response order.

# ====== Standard Library Imports ======
from collections.abc import Callable
from typing import Any

# ====== Local Project Imports ======
from ..models import RerankItem
from .batch_processor import BatchProcessor


class RerankProcessor(BatchProcessor):
    """Processes batches of the rerank worker (TEI-shaped scores per request)."""

    item_type = RerankItem

    def _payload(self, item: Any) -> list[Any]:
        """Return the ``[query, text]`` pair of every candidate text of the item."""
        return [[item.query, text] for text in item.texts]

    def _model_call(self) -> Callable[[list[Any]], list[Any]]:
        """Return the flat pair-scoring call of the model service."""
        return self._models.compute_rerank_scores_flat

    def _shape_result(self, rows: list[Any]) -> Any:
        """Re-number indices 0..n-1 for the request and sort them score-descending."""
        return sorted(
            ({"index": i, "score": float(s)} for i, s in enumerate(rows)),
            key=lambda r: r["score"],
            reverse=True,
        )
