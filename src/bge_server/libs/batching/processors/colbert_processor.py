# ====== Code Summary ======
# ColbertProcessor: batched ColBERT multi-vector embedding path. Runs
# BgeModelsService.encode_colbert over the flattened texts under embed_lock; each item's future
# resolves to its slice of per-token vector lists (variable token count per text).

# ====== Standard Library Imports ======
from collections.abc import Callable
from typing import Any

# ====== Local Project Imports ======
from .embed_batch_processor import EmbedBatchProcessor


class ColbertProcessor(EmbedBatchProcessor):
    """Processes batches of the colbert worker (one list of token vectors per text)."""

    def _model_call(self) -> Callable[[list[Any]], list[Any]]:
        """Return the colbert encode call bound to the engine's max_length."""
        max_length = self._max_length
        return lambda chunk: self._models.encode_colbert(chunk, max_length)

    def _shape_result(self, rows: list[Any]) -> Any:
        """Resolve the item to its per-token vector lists, one per text."""
        return rows
