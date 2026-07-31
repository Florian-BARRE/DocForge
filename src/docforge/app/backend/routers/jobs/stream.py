# ====== Code Summary ======
# The live SSE feed of one ingestion job — a DB-poll-backed Server-Sent Events generator (NO message
# bus). It polls the persisted job row + its stage-event table on a short interval and yields only
# what is NEW: each freshly-landed stage event, and a status frame whenever the status snapshot
# changes. It stops (closing the stream) as soon as the job reaches a terminal state. The generator
# takes the jobs facade as an argument (not CONTEXT) so it drives against a fake in unit tests.

# ====== Standard Library Imports ======
import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

# ====== Local Project Imports ======
from .models import JobEvent, JobStatus

# The job states after which nothing more will land — the stream closes on reaching one.
_TERMINAL = {"done", "failed"}


def _frame(kind: str, payload: dict[str, Any]) -> str:
    """Render one well-formed SSE frame — ``data: {json}\\n\\n`` with the frame kind inside the JSON."""
    return f"data: {json.dumps({'kind': kind, **payload}, default=str)}\n\n"


async def stream_job_events(
    jobs: Any,
    job_id: uuid.UUID,
    *,
    poll_interval: float = 0.75,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[str]:
    """
    Yield an SSE frame stream of a job's live progress until it terminates, then close.

    Polls the persisted job row + stage-event timeline every ``poll_interval`` seconds and emits
    only the delta: each newly-landed stage event (``kind: "event"``) in order, plus a status frame
    (``kind: "status"``) whenever the status snapshot changes (so progress advances flow through). A
    final status frame always lands because a terminal status differs from the running one. The loop
    returns as soon as the job is done/failed, which ends the HTTP response.

    Args:
        jobs (Any): The jobs facade (anything exposing async ``get`` + ``list_events``) — passed in
            so tests can drive the generator against a fake.
        job_id (uuid.UUID): The job to stream.
        poll_interval (float): Seconds between polls (short — this is a poll-backed SSE, no bus).
        sleep (Callable): The awaitable sleep (injected so tests run with no real delay).

    Yields:
        str: One SSE frame per new event and per status change, terminated by the final status.
    """
    cursor = 0  # number of stage events already emitted (the delta cursor)
    last_snapshot: dict[str, Any] | None = None
    while True:
        # 1. Re-read the row — the worker owns it; a vanished job (deleted mid-stream) closes cleanly.
        job = await jobs.get(job_id)
        if job is None:
            yield _frame("status", {"job_id": str(job_id), "status": "gone"})
            return

        # 2. Emit every stage event that landed since the last poll, in execution order.
        events = await jobs.list_events(job_id)
        for event in events[cursor:]:
            yield _frame("event", JobEvent.from_row(event).model_dump(mode="json"))
        cursor = len(events)

        # 3. Emit a status frame only when the snapshot moved (status/progress/stage/error), so the
        #    stream carries progress without spamming an unchanged status every tick.
        snapshot = JobStatus.from_row(job).model_dump(mode="json")
        if snapshot != last_snapshot:
            yield _frame("status", snapshot)
            last_snapshot = snapshot

        # 4. Terminal → the final status is already out; close the stream.
        if job.status.value in _TERMINAL:
            return
        await sleep(poll_interval)


__all__ = ["stream_job_events"]
