# ====== Code Summary ======
# HeartbeatWriter — a lightweight background loop that refreshes the worker's liveness row every
# few seconds, REGARDLESS of load. It is what makes an idle-but-alive worker visible and a dead
# worker detectable fast (stale last_seen) instead of only via the 600s stall / reaper. One
# responsibility: periodically upsert worker_heartbeats for this worker's stable id.

# ====== Standard Library Imports ======
import asyncio
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db import Database


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
        interval_seconds: int,
    ) -> None:
        LoggerClass.__init__(self)
        self._database = database
        self._worker_id = worker_id
        self._interval = interval_seconds
        self._started_at = datetime.now(UTC)
        self._task: asyncio.Task[None] | None = None

    async def __tick(self) -> None:
        """Write one heartbeat, swallowing any DB error so the loop survives a transient blip."""
        try:
            await self._database.jobs.upsert_heartbeat(
                self._worker_id, datetime.now(UTC), self._started_at
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


__all__ = ["HeartbeatWriter"]
