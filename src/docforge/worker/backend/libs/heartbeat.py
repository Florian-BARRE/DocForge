# ====== Code Summary ======
# HeartbeatWriter — a lightweight background loop that refreshes the worker's liveness row every
# few seconds, REGARDLESS of load. It is what makes an idle-but-alive worker visible and a dead
# worker detectable fast (stale last_seen) instead of only via the 600s stall / reaper. One
# responsibility: periodically upsert worker_heartbeats for this worker's stable id.

# ====== Standard Library Imports ======
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
import psutil
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db import Database

# Bytes-per-megabyte divisor for turning psutil's RSS (bytes) into megabytes.
_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResourceSample:
    """
    One immutable snapshot of a worker process's CPU/memory usage.

    Every field is nullable: a psutil error turns the whole sample into all-None so the heartbeat
    still writes (telemetry must never crash liveness). ``cpu_percent`` may exceed 100 on a
    multi-core host (percent-of-one-core semantics) and reads 0.0 on the first, unprimed tick.

    Attributes:
        cpu_percent (float | None): Recent CPU utilisation percent since the previous sample.
        mem_mb (float | None): Resident set size (RSS) in megabytes.
        mem_percent (float | None): Resident memory as a percent of total host RAM.
    """

    cpu_percent: float | None
    mem_mb: float | None
    mem_percent: float | None


class HeartbeatWriter(LoggerClass):
    """
    Periodically refreshes a worker's liveness heartbeat row for the length of its lifetime.

    Runs as a single background asyncio task: one immediate tick at start (so the worker is visible
    the instant it is ready), then one tick every ``interval_seconds`` until stopped. Failures to
    write are logged and swallowed — a transient DB blip must never take the worker down.
    """

    def __init__(
        self,
        database: Database,
        worker_id: str,
        worker_name: str,
        interval_seconds: int,
        max_jobs: int,
    ) -> None:
        LoggerClass.__init__(self)
        self._database = database
        self._worker_id = worker_id
        self._worker_name = worker_name
        self._interval = interval_seconds
        self._max_jobs = max_jobs
        self._started_at = datetime.now(UTC)
        self._task: asyncio.Task[None] | None = None
        # A PERSISTENT handle on THIS worker process: psutil.Process().cpu_percent(interval=None)
        # reports utilisation since its PREVIOUS call on the same object, so the handle must survive
        # across ticks. The first tick reads 0.0 (no prior reference); every later tick is real.
        self._process = psutil.Process()

    def __sample_resources(self) -> ResourceSample:
        """
        Sample THIS worker process's CPU/memory once, returning all-None on any psutil error.

        Returns:
            ResourceSample: The current CPU/memory snapshot; every field is None if sampling failed
                (telemetry must never crash the heartbeat).
        """
        try:
            # 1. CPU since the previous call on the persistent handle (0.0 on the first, unprimed tick;
            #    may exceed 100 on a multi-core host — never clamp).
            cpu_percent = self._process.cpu_percent(interval=None)

            # 2. Resident memory: absolute megabytes and percent-of-host-RAM.
            mem_mb = self._process.memory_info().rss / _BYTES_PER_MB
            mem_percent = self._process.memory_percent()

            # 3. Fold into an immutable snapshot.
            return ResourceSample(cpu_percent=cpu_percent, mem_mb=mem_mb, mem_percent=mem_percent)
        except Exception as exc:  # noqa: BLE001 — telemetry must never crash the heartbeat
            self.logger.warning(f"Resource sampling failed for '{self._worker_id}': {exc}")
            return ResourceSample(cpu_percent=None, mem_mb=None, mem_percent=None)

    async def __tick(self) -> None:
        """Write one heartbeat, swallowing any DB error so the loop survives a transient blip."""
        try:
            # 1. Sample this process's live CPU/memory (all-None on a psutil error, never raising).
            sample = self.__sample_resources()

            # 2. Upsert the liveness row. The reported capacity is the worker's arq concurrency
            #    (WORKER_CONCURRENCY, = WorkerSettings.max_jobs) — it lets the UI show a "N running /
            #    max" chip — alongside the just-sampled resource usage.
            await self._database.jobs.upsert_heartbeat(
                self._worker_id,
                self._worker_name,
                datetime.now(UTC),
                self._started_at,
                self._max_jobs,
                cpu_percent=sample.cpu_percent,
                mem_mb=sample.mem_mb,
                mem_percent=sample.mem_percent,
            )
        except Exception as exc:  # noqa: BLE001 — liveness must never crash the worker
            self.logger.warning(f"Heartbeat write failed for '{self._worker_id}': {exc}")

    async def __loop(self) -> None:
        """Beat immediately, then once per interval until the task is cancelled."""
        await self.__tick()
        while True:
            await asyncio.sleep(self._interval)
            await self.__tick()

    def start(self) -> None:
        """Spawn the background heartbeat loop (idempotent — a second call is a no-op)."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self.__loop())
        self.logger.info(
            f"Heartbeat writer started for '{self._worker_id}' (every {self._interval}s)"
        )

    async def stop(self) -> None:
        """
        Cancel the background loop, then de-register this worker's heartbeat row.

        The row is DELETED on a clean shutdown so the worker disappears from the fleet immediately
        (rather than lingering as a stale "off" card until the read-side prune ages it out). The
        delete is best-effort: a shutdown-time DB error is logged and swallowed so it can never crash
        an otherwise-clean shutdown — the read-side prune is the backstop for a row left behind.
        """
        # 1. Stop beating first, so no tick can re-insert the row after we delete it.
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # 2. Remove our own liveness row (best-effort — never fail a clean shutdown over it).
        try:
            await self._database.jobs.delete_heartbeat(self._worker_id)
        except Exception as exc:  # noqa: BLE001 — de-registration must never crash shutdown
            self.logger.warning(f"Heartbeat de-register failed for '{self._worker_id}': {exc}")


__all__ = ["HeartbeatWriter", "ResourceSample"]
