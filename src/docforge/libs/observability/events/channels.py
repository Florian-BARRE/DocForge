# ====== Code Summary ======
# Event channel + type constants for the observability pub/sub bus. A single Redis channel
# carries all monitoring events; consumers (the SSE broadcaster in brique C) filter on the
# typed ``type`` field of each payload. One channel keeps cross-process fan-out simple.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum

# Single pub/sub channel for every monitoring event. Workers publish here; the backend SSE layer
# (brique C) subscribes and fans out to browsers.
EVENTS_CHANNEL: str = "docforge:events"


class EventType(StrEnum):
    """Typed discriminator carried in every event payload's ``type`` field."""

    JOB_UPDATED = "job.updated"
    STAGE_PROGRESS = "stage.progress"
    WORKER_HEARTBEAT = "worker.heartbeat"
    BATCH_UPDATED = "batch.updated"


# ------------------- Public API ------------------- #
__all__ = ["EVENTS_CHANNEL", "EventType"]
