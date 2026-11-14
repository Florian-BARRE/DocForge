# ====== Code Summary ======
# DenseProcessor: batched dense embedding path. Runs BgeModelsService.encode_dense over the
# flattened texts under embed_lock; each item's future resolves to its slice of dense vectors.

# ====== Standard Library Imports ======
from collections.abc import Callable
from typing import Any

# ====== Local Project Imports ======
from .embed_batch_processor import EmbedBatchProcessor


class DenseProcessor(EmbedBatchProcessor):
    """Processes batches of the dense worker (one 1024-dim vector per text)."""

    def _model_call(self) -> Callable[[list[Any]], list[Any]]:
        """Return the dense encode call bound to the engine's max_length."""
        max_length = self._max_length
        return lambda chunk: self._models.encode_dense(chunk, max_length)

    def _shape_result(self, rows: list[Any]) -> Any:
        """Resolve the item to its dense vectors, one per text."""
        return rows
