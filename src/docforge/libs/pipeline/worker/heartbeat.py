# ====== Code Summary ======
# WorkerHeartbeatLoop — the periodic task each arq worker runs to publish its liveness/load
# snapshot. Reads mutable runtime state (current job, jobs processed) from the shared arq ctx,
# samples resource gauges, writes the heartbeat to Redis (TTL'd) and publishes a heartbeat event.
# Telemetry only — a failure to beat is logged and never propagated to the pipeline.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.observability.events import EventPublisher
from libs.observability.heartbeat import HeartbeatWriter, WorkerHeartbeat
from libs.observability.metrics import MetricsCollector


class WorkerHeartbeatLoop(LoggerClass):
    """
    Periodic heartbeat publisher for a single arq worker process.

    Runs as a background asyncio task spawned at worker startup and cancelled at shutdown. Each
    tick samples resource gauges and reports liveness; the shared ``ctx`` dict supplies the
    live job id and processed-jobs counter that the task functions mutate.
    """

    def __init__(
        self,
        *,
        writer: HeartbeatWriter,
        publisher: EventPublisher,
        metrics: MetricsCollector,
        ctx: dict,
        worker_id: str,
        hostname: str,
        pid: int,
        interval_s: int,
    ) -> None:
        """
        Initialize the heartbeat loop.

        Args:
            writer (HeartbeatWriter): TTL'd Redis heartbeat writer.
            publisher (EventPublisher): Pub/sub publisher for ``worker.heartbeat`` events.
            metrics (MetricsCollector): Resource gauge sampler (psutil + NVML).
            ctx (dict): Shared arq context — read for ``current_job_id`` / ``jobs_processed``.
            worker_id (str): Stable worker id (``hostname:pid:rand``).
            hostname (str): Host the worker runs on.
            pid (int): OS process id.
            interval_s (int): Seconds between heartbeats.
        """
        LoggerClass.__init__(self)
        self._writer = writer
        self._publisher = publisher
        self._metrics = metrics
        self._ctx = ctx
        self._worker_id = worker_id
        self._hostname = hostname
        self._pid = pid
        self._interval_s = interval_s
        self._started_at = datetime.now(UTC).isoformat()

    async def __beat_once(self) -> None:
        """Sample gauges and write + publish one heartbeat (best-effort)."""
        # 1. Read live state mutated by the task functions
        current_job_id = self._ctx.get("current_job_id")
        jobs_processed = int(self._ctx.get("jobs_processed", 0))

        # 2. Sample resource gauges (empty dict when metrics are disabled)
        snap = self._metrics.snapshot()

        # 3. Assemble the heartbeat snapshot
        heartbeat = WorkerHeartbeat(
            worker_id=self._worker_id,
            hostname=self._hostname,
            pid=self._pid,
            started_at=self._started_at,
            last_seen=datetime.now(UTC).isoformat(),
            status="busy" if current_job_id else "idle",
            current_job_id=current_job_id,
            jobs_processed=jobs_processed,
            cpu_pct=float(snap.get("cpu_pct", 0.0)),
            rss_mb=float(snap.get("rss_mb", 0.0)),
            sys_cpu_pct=float(snap.get("sys_cpu_pct", 0.0)),
            sys_ram_pct=float(snap.get("sys_ram_pct", 0.0)),
            gpu=list(snap.get("gpu", []) or []),
        )

        # 4. Persist (Redis, TTL'd) + fan out an event; swallow telemetry failures
        try:
            await self._writer.beat(heartbeat)
            await self._publisher.worker_heartbeat(heartbeat.to_dict())
        except Exception as exc:
            self.logger.warning(f"Heartbeat write/publish failed ({exc}).")

    async def run(self) -> None:
        """
        Run the heartbeat loop until cancelled.

        On cancellation, the worker's heartbeat key is removed so the worker disappears from the
        dashboard immediately on a clean shutdown rather than after the TTL elapses.
        """
        # 1. Beat on a fixed cadence until the task is cancelled at shutdown
        self.logger.info(f"Heartbeat loop started for worker {self._worker_id} (every {self._interval_s}s).")
        try:
            while True:
                await self.__beat_once()
                await asyncio.sleep(self._interval_s)
        except asyncio.CancelledError:
            # 2. Clean shutdown — drop the key, then re-raise to let the task finish
            await self._writer.remove()
            self.logger.info(f"Heartbeat loop stopped for worker {self._worker_id}.")
            raise


# ------------------- Public API ------------------- #
__all__ = ["WorkerHeartbeatLoop"]
