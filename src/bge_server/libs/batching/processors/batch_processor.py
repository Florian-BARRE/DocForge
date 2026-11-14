# ====== Code Summary ======
# BatchProcessor: abstract template for one batched inference path. The BatchQueueWorker hands a
# formed batch to ``process``; the processor flattens every item's payload into one list, runs the
# blocking model call over it in sub-batches (under the global admission gate and the model lock,
# via asyncio.to_thread), and scatters the results back to each item's future. Per-item error
# isolation: any failure is set on every pending future of the batch so no HTTP request hangs.
# Concrete processors (dense / sparse / colbert / embed_all / rerank) only say which item type they
# serve, which model call to run, and how one item's slice of the results is shaped.

# ====== Standard Library Imports ======
import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from ..models import BatchItem

if TYPE_CHECKING:
    from libs.bge_models.service import BgeModelsService


class BatchProcessor(LoggerClass, ABC):
    """
    Template for one batched inference path (flatten -> sub-batched model call -> scatter).

    Subclasses set ``item_type`` and implement ``_model_call`` and ``_shape_result``; they may
    override ``_payload`` when an item contributes something other than its plain texts (rerank).
    """

    item_type: ClassVar[type[BatchItem]]

    def __init__(
        self,
        models: "BgeModelsService",
        gate: asyncio.Semaphore,
        lock: asyncio.Lock,
        sub_batch_size: int,
    ) -> None:
        """
        Args:
            models (BgeModelsService): Loaded BGE model service the model call runs on.
            gate (asyncio.Semaphore): Global admission gate shared by every processor: at most
                ``max_concurrent`` forward passes in flight service-wide.
            lock (asyncio.Lock): Lock of the model instance this path calls. The four embed
                paths share one (one embed_model instance); rerank has its own.
            sub_batch_size (int): Texts/pairs per model call inside a formed batch (0 = one call
                for the whole batch). Between calls, work nobody is waiting for is dropped.
        """
        LoggerClass.__init__(self)
        self._models = models
        self._gate = gate
        self._lock = lock
        self._sub_batch_size = sub_batch_size

    # ── Contract implemented by each path ──────────────────────────────────────

    @abstractmethod
    def _model_call(self) -> Callable[[list[Any]], list[Any]]:
        """
        Return the blocking model call, one result per entry of the slice it receives.

        Returns:
            Callable: Function run in a worker thread over a slice of the flattened payload.
        """

    @abstractmethod
    def _shape_result(self, rows: list[Any]) -> Any:
        """
        Build one item's future result from its slice of the flat model results.

        Args:
            rows (list): The flat results that belong to the item, in order.

        Returns:
            Any: The value the item's future resolves to.
        """

    def _payload(self, item: Any) -> list[Any]:
        """
        Return the entries one item contributes to the flat payload (its texts by default).

        Args:
            item (BatchItem): The batch item.

        Returns:
            list: The entries appended to the flat list for this item.
        """
        return list(item.texts)

    # ── Template ───────────────────────────────────────────────────────────────

    async def process(self, batch: list[BatchItem]) -> None:
        """
        Flatten, run the model call under gate + model lock, scatter results back.

        Args:
            batch (list[BatchItem]): Batch handed over by this path's BatchQueueWorker; items of
                another type (none in practice) are ignored.
        """
        items = [i for i in batch if isinstance(i, self.item_type)]
        try:
            # 1. Flatten all payloads and record per-item offsets for scatter
            flat, offsets, owners = self._flatten(items)

            # 2. Sub-batched model call under gate + model lock
            results = await self._infer(items, flat, owners, self._model_call())

            # 3. Scatter results back to each item's future by slice
            for item, (start, end) in zip(items, offsets):
                if not item.future.done():
                    item.future.set_result(self._shape_result(results[start:end]))

        except Exception as exc:
            # Error isolation: distribute failure to every future so no request hangs
            for item in items:
                if not item.future.done():
                    item.future.set_exception(exc)

    def _flatten(self, items: list[Any]) -> tuple[list[Any], list[tuple[int, int]], list[int]]:
        """
        Flatten every item's payload into one list.

        Args:
            items (list): Batch items of this path's ``item_type``.

        Returns:
            tuple: ``(flat, offsets, owners)`` -- the flat payload list, each item's
                ``(start, end)`` slice into it, and the owning item index of every flat entry.
        """
        flat: list[Any] = []
        offsets: list[tuple[int, int]] = []
        owners: list[int] = []
        for index, item in enumerate(items):
            start = len(flat)
            flat.extend(self._payload(item))
            offsets.append((start, len(flat)))
            owners.extend([index] * (len(flat) - start))
        return flat, offsets, owners

    async def _infer(
        self,
        items: list[Any],
        flat: list[Any],
        owners: list[int],
        call: Callable[[list[Any]], list[Any]],
    ) -> list[Any]:
        """
        Run ``call`` over ``flat`` in sub-batches, dropping work nobody is waiting for.

        Takes the global admission gate then the model lock. A forward pass runs in a thread and
        cannot be interrupted, so cancellation only takes effect at the checks here: before the
        first pass (the request may have died while queued on the gate/lock) and between every
        sub-batch. A sub-batch is skipped only when EVERY item that owns one of its entries has
        been cancelled (client disconnected), so live requests are never short-changed.

        Args:
            items (list): The batch items, whose futures say whether anyone still waits.
            flat (list): Flattened payload entries.
            owners (list[int]): Owning item index per flat entry.
            call (Callable): Blocking model call over a slice of ``flat``, one result per entry.

        Returns:
            list: One result per flat entry; ``None`` for entries skipped as abandoned.
        """
        results: list[Any] = [None] * len(flat)
        size = self._sub_batch_size if self._sub_batch_size > 0 else max(1, len(flat))
        async with self._gate, self._lock:
            for start in range(0, len(flat), size):
                end = min(start + size, len(flat))
                if all(items[o].future.done() for o in set(owners[start:end])):
                    continue
                results[start:end] = await asyncio.to_thread(call, flat[start:end])
        return results
