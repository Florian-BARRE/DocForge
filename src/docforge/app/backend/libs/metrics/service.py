# ====== Code Summary ======
# MetricsService — refreshes the DocForge infra gauges at scrape time and renders the full Prometheus
# exposition. The HTTP series are fed passively by HttpMetricsMiddleware; this service adds the
# operational gauges the UI does NOT expose as scrapable: the arq queue depth (Redis), job counts by
# state and the live-worker count (both from the observability facade). Each source is best-effort and
# the whole refresh is bounded by a scrape timeout, so a degraded store never wedges a scrape — the
# HTTP series and the gauge definitions always render, the infra gauges simply keep their last value.

# ====== Standard Library Imports ======
import asyncio
from datetime import UTC, datetime
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# ====== Internal Project Imports ======
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import JobStatus

# ====== Local Project Imports ======
from ...utils.queue import QueueClient
from .collectors import DocForgeMetrics


class MetricsService(LoggerClass):
    """Refreshes the infra gauges and renders the Prometheus exposition for the /metrics endpoint."""

    def __init__(
        self,
        database: Database,
        queue: QueueClient,
        *,
        scrape_timeout_seconds: float,
        worker_alive_threshold_seconds: float,
    ) -> None:
        """
        Args:
            database (Database): The store façade (source of job counts + worker heartbeats).
            queue (QueueClient): The arq queue client (source of the Redis queue depth).
            scrape_timeout_seconds (float): Wall-clock cap for one scrape's infra-gauge refresh.
            worker_alive_threshold_seconds (float): A heartbeat fresher than this counts as alive.
        """
        LoggerClass.__init__(self)
        self._database = database
        self._queue = queue
        self._scrape_timeout = scrape_timeout_seconds
        self._alive_threshold = worker_alive_threshold_seconds

    @property
    def content_type(self) -> str:
        """The Prometheus exposition content type (for the HTTP response media type)."""
        return CONTENT_TYPE_LATEST

    async def render(self) -> bytes:
        """
        Refresh the infra gauges (best-effort, bounded) and render the whole registry as text.

        Returns:
            bytes: The Prometheus exposition (HTTP series + infra gauges) in text/plain format.
        """
        # 1. Best-effort infra refresh, bounded so a degraded store can never wedge the scrape.
        try:
            await asyncio.wait_for(self._refresh_infra_gauges(), timeout=self._scrape_timeout)
        except Exception as exc:
            self.logger.warning(f"Metrics infra refresh degraded (gauges kept last value): {exc}")

        # 2. Render the whole default registry (HTTP series + infra gauges) as Prometheus text.
        return generate_latest()

    async def _refresh_infra_gauges(self) -> None:
        """Refresh each infra gauge from its source; a per-source failure never aborts the others."""
        # 1. Each source is independently best-effort so a single store outage still lets the rest
        #    refresh (the outer wait_for bounds the total time against a hard network hang).
        await self._refresh_queue_depth()
        await self._refresh_job_counts()
        await self._refresh_worker_count()

    async def _refresh_queue_depth(self) -> None:
        """Set the arq queue-depth gauge from Redis (unclaimed ingestion backlog)."""
        # 1. A Redis outage leaves the gauge at its last value rather than failing the scrape.
        try:
            DocForgeMetrics.ARQ_QUEUE_DEPTH.set(await self._queue.queue_depth())
        except Exception as exc:
            self.logger.warning(f"arq queue-depth gauge skipped this scrape: {exc}")

    async def _refresh_job_counts(self) -> None:
        """Set the pending / running / failed job gauges from one grouped DB read."""
        # 1. One grouped count feeds three gauges; a DB outage leaves them at their last value.
        try:
            counts = await self._database.jobs.status_counts()
            DocForgeMetrics.JOBS_PENDING.set(counts.get(JobStatus.PENDING, 0))
            DocForgeMetrics.JOBS_RUNNING.set(counts.get(JobStatus.RUNNING, 0))
            DocForgeMetrics.JOBS_FAILED.set(counts.get(JobStatus.FAILED, 0))
        except Exception as exc:
            self.logger.warning(f"job-count gauges skipped this scrape: {exc}")

    async def _refresh_worker_count(self) -> None:
        """Set the live-worker gauge from the heartbeat table (fresh-heartbeat count)."""
        # 1. Count heartbeats fresher than the alive threshold; a DB outage keeps the last value.
        try:
            heartbeats = await self._database.jobs.list_heartbeats()
            DocForgeMetrics.WORKERS_LIVE.set(self._count_live_workers(heartbeats))
        except Exception as exc:
            self.logger.warning(f"live-worker gauge skipped this scrape: {exc}")

    def _count_live_workers(self, heartbeats: list[Any]) -> int:
        """
        Count heartbeats whose last-seen instant is within the liveness threshold.

        Args:
            heartbeats (list[Any]): The worker_heartbeats rows (each exposing ``last_seen``).

        Returns:
            int: The number of workers currently considered alive.
        """
        # 1. Mirror the fleet view's liveness rule: fresh-enough last_seen counts as alive.
        now = datetime.now(UTC)
        live = 0
        for heartbeat in heartbeats:
            last_seen = heartbeat.last_seen
            if last_seen is None:
                continue
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            if (now - last_seen).total_seconds() <= self._alive_threshold:
                live += 1
        return live


__all__ = ["MetricsService"]
