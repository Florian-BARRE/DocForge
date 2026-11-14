# ====== Code Summary ======
# SparseProcessor: batched sparse (lexical) embedding path. Runs BgeModelsService.encode_sparse
# over the flattened texts under embed_lock; each item's future resolves to its slice of TEI-shaped
# token lists.

# ====== Standard Library Imports ======
from collections.abc import Callable
from typing import Any

# ====== Local Project Imports ======
from .embed_batch_processor import EmbedBatchProcessor


class SparseProcessor(EmbedBatchProcessor):
    """Processes batches of the sparse worker (one token list per text)."""

    def _model_call(self) -> Callable[[list[Any]], list[Any]]:
        """Return the sparse encode call bound to the engine's max_length."""
        max_length = self._max_length
        return lambda chunk: self._models.encode_sparse(chunk, max_length)

    def _shape_result(self, rows: list[Any]) -> Any:
        """Resolve the item to its sparse token lists, one per text."""
        return rows
