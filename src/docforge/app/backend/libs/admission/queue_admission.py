# ====== Code Summary ======
# QueueAdmission — backpressure on BULK enqueues. The worker drains the arq queue at
# WORKER_CONCURRENCY, so repeated bulk calls (each individually under CORPUS_MAX_REINGEST_FANOUT) used
# to stack an unbounded backlog. A bulk fan-out of ``n`` jobs is refused with 429 + Retry-After when
# ``depth + n`` would exceed QUEUE_MAX_DEPTH. A SINGLE upload/reingest is deliberately NOT gated here:
# one job can always be admitted (a user must never be locked out of uploading one file by a bulk
# backlog); the hard bound on the backlog is the sum of capped bulk calls, which this check holds.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from ...utils.queue import QueueClient


class QueueAdmission(LoggerClass):
    """Refuses a bulk enqueue that would push the queue past its configured maximum depth."""

    def __init__(self, queue: QueueClient, max_depth: int, retry_after_seconds: int) -> None:
        """
        Args:
            queue (QueueClient): The queue whose depth (the arq ZSET) is read.
            max_depth (int): QUEUE_MAX_DEPTH. <= 0 disables the check.
            retry_after_seconds (int): The ``Retry-After`` hint sent with a refusal.
        """
        LoggerClass.__init__(self)
        self._queue = queue
        self._max_depth = max_depth
        self._retry_after = retry_after_seconds

    async def check_bulk(self, n: int) -> None:
        """
        Admit a bulk enqueue of ``n`` jobs, or raise 429.

        Call it ONCE per bulk request, with the number of jobs about to be enqueued (after the
        fan-out cap and the in-flight skip), BEFORE the first ``enqueue_ingest``.

        Args:
            n (int): How many jobs the caller is about to enqueue.

        Raises:
            HTTPException: 429 with a ``Retry-After`` header and a structured ``queue_saturated``
                detail when ``depth + n > QUEUE_MAX_DEPTH``.
        """
        # 1. Disabled, or nothing to enqueue → pass.
        if self._max_depth <= 0 or n <= 0:
            return
        # 2. Read the live backlog; an unreadable queue fails OPEN (the enqueue itself will surface a
        #    real Redis outage where it matters — this guard must not invent a second failure mode).
        try:
            depth = await self._queue.queue_depth()
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"Queue depth unreadable ({error!r}) — bulk admission fails open")
            return
        # 3. Refuse when the whole fan-out would not fit under the ceiling.
        if depth + n > self._max_depth:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "queue_saturated",
                    "message": (
                        f"The ingestion queue holds {depth} job(s); enqueuing {n} more would exceed "
                        f"the {self._max_depth} limit. Retry once the backlog drains."
                    ),
                    "queue_depth": depth,
                    "requested": n,
                    "max_depth": self._max_depth,
                },
                headers={"Retry-After": str(self._retry_after)},
            )


__all__ = ["QueueAdmission"]
