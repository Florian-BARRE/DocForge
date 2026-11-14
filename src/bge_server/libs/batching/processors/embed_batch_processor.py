# ====== Code Summary ======
# EmbedBatchProcessor: base of the four embed paths (dense / sparse / colbert / embed_all). They
# all consume EmbedItem-shaped payloads (texts), share the embed_model instance (hence one
# embed_lock, handed in by the engine) and forward the engine's configured tokenizer max_length
# to the model call.

# ====== Standard Library Imports ======
import asyncio
from typing import TYPE_CHECKING, ClassVar

# ====== Local Project Imports ======
from ..models import BatchItem, EmbedItem
from .batch_processor import BatchProcessor

if TYPE_CHECKING:
    from libs.bge_models.service import BgeModelsService


class EmbedBatchProcessor(BatchProcessor):
    """Common base of the embed-family processors: EmbedItem payloads plus a max_length."""

    item_type: ClassVar[type[BatchItem]] = EmbedItem

    def __init__(
        self,
        models: "BgeModelsService",
        gate: asyncio.Semaphore,
        lock: asyncio.Lock,
        sub_batch_size: int,
        max_length: int,
    ) -> None:
        """
        Args:
            models (BgeModelsService): Loaded BGE model service.
            gate (asyncio.Semaphore): Global admission gate.
            lock (asyncio.Lock): The embed_lock shared by every embed-family path.
            sub_batch_size (int): Texts per model call inside a formed batch (0 = whole batch).
            max_length (int): Tokenizer max length forwarded to the encode call (BGE_M3_MAX_LENGTH).
        """
        super().__init__(models, gate, lock, sub_batch_size)
        self._max_length = max_length
