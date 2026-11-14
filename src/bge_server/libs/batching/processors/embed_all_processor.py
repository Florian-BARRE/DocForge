# ====== Code Summary ======
# EmbedAllProcessor: batched combined dense+sparse path (the PRIMARY production path). Runs
# BgeModelsService.encode_dense_sparse -- ONE forward pass per sub-batch over the cross-request
# batch -- under embed_lock. Each item's future resolves to a ``(dense_slice, sparse_slice)`` tuple.

# ====== Standard Library Imports ======
from collections.abc import Callable
from typing import Any

# ====== Local Project Imports ======
from ..models import EmbedAllItem
from .embed_batch_processor import EmbedBatchProcessor


class EmbedAllProcessor(EmbedBatchProcessor):
    """Processes batches of the embed_all worker (a (dense, sparse) pair per request)."""

    item_type = EmbedAllItem

    def _model_call(self) -> Callable[[list[Any]], list[Any]]:
        """Return a call yielding one ``(dense, sparse)`` pair per text from a single pass."""

        def combined(chunk: list[Any]) -> list[Any]:
            dense, sparse = self._models.encode_dense_sparse(chunk, self._max_length)
            return list(zip(dense, sparse))

        return combined

    def _shape_result(self, rows: list[Any]) -> Any:
        """Split the per-text pairs into the ``(dense_list, sparse_list)`` tuple."""
        return ([r[0] for r in rows], [r[1] for r in rows])
