# ====== Code Summary ======
# Dataclass models for the dynamic-batching engine: BatchItem (base), EmbedItem, RerankItem.
# Each item carries an asyncio.Future (resolved when the batch result is scattered back) and a
# cost (number of units this item contributes to the batch budget — texts for embed/sparse,
# pairs for rerank). QueueFullError signals back-pressure to the HTTP layer.

# ====== Standard Library Imports ======
import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class BatchItem:
    """
    Base class for a single request enqueued for batched inference.

    Attributes:
        future (asyncio.Future): Resolved with the scatter result when the batch completes,
            or set with an exception when the batch fails. Created by the engine before submit.
        cost (int): Number of units this item contributes to the batch budget.
            For embed/sparse items: len(texts). For rerank items: len(texts) (pair count).
    """

    future: asyncio.Future
    cost: int


@dataclass(slots=True)
class EmbedItem(BatchItem):
    """
    A single embed (dense or sparse) request waiting in the batch queue.

    Attributes:
        texts (list[str]): The texts to embed. cost == len(texts).
    """

    texts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RerankItem(BatchItem):
    """
    A single rerank request waiting in the batch queue.

    Attributes:
        query (str): The search query for the cross-encoder.
        texts (list[str]): Candidate texts to score against the query. cost == len(texts).
    """

    query: str = ""
    texts: list[str] = field(default_factory=list)


class QueueFullError(Exception):
    """
    Raised by BatchQueueWorker.submit() when the bounded queue is at capacity.

    The inference router translates this into an HTTP 503 with a Retry-After header,
    signalling the client that the server is temporarily overloaded.
    """
