# ====== Code Summary ======
# The `worker_heartbeats` table — one row per worker process, upserted on a fixed interval regardless
# of load. It makes an idle-but-alive worker observable (last_seen fresh, no running job) and a dead
# worker detectable (stale last_seen) without relying on the 10-minute job stall / reaper signal.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base


class WorkerHeartbeat(Base):
    """A worker process's liveness heartbeat, keyed by its stable worker id."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # A human-friendly display label for the worker (WORKER_NAME, defaults to the hostname). Kept
    # alongside worker_id so the UI can show "what is ingesting" without exposing only a hostname;
    # NULL for a row written before this column landed (the read falls back to worker_id).
    worker_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Refreshed on every heartbeat tick (~10s); its age is the liveness signal.
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set once when the worker first registers; lets the UI show process uptime.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The worker's configured arq concurrency: how many ingestion jobs it can run at once. Paired with
    # the live running-job count, it lets the UI render "N running / max" per worker. NULL when unknown:
    # a heartbeat row written before this column landed, or a worker on an older build that does not
    # report its capacity yet (the UI treats NULL as "unknown capacity").
    max_jobs: Mapped[int | None] = mapped_column(Integer, nullable=True)


__all__ = ["WorkerHeartbeat"]
