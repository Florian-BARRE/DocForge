# ====== Code Summary ======
# MonitoringHelpers — static assembly logic for the monitoring router: convert heartbeats to API
# models, build the queue/worker snapshots from the injected services, and produce the static
# discovery descriptors. Keeping the multi-source orchestration here (not in router.py) honours
# the rule that router files hold only route definitions.

# ====== Standard Library Imports ======
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.observability.heartbeat import WorkerHeartbeat

# ====== Local Project Imports ======
from .models import (
    MonitoringDiscoveryResponse,
    PanelDescriptor,
    QueueStatusResponse,
    WorkerInfo,
    WorkersResponse,
)

if TYPE_CHECKING:
    from libs.observability.heartbeat import HeartbeatReader
    from libs.observability.queue import QueueIntrospector
    from libs.storage.postgres.client import PostgresClient
    from libs.storage.postgres.repositories import JobRepository

# Throughput averaging window (minutes) used by the queue endpoint.
THROUGHPUT_WINDOW_MINUTES: int = 5


class MonitoringHelpers:
    """Static helpers for assembling monitoring responses from injected services."""

    logger = loggerplusplus.bind(identifier="MonitoringHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("MonitoringHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def to_worker_info(heartbeat: WorkerHeartbeat) -> WorkerInfo:
        """
        Convert an observability heartbeat into the API worker model.

        Args:
            heartbeat (WorkerHeartbeat): Heartbeat read from Redis.

        Returns:
            WorkerInfo: Validated API representation.
        """
        # model_validate maps the heartbeat dict (incl. the gpu gauge list) onto the model.
        return WorkerInfo.model_validate(heartbeat.to_dict())

    @classmethod
    async def build_queue_status(
        cls,
        *,
        queue_introspector: QueueIntrospector,
        postgres: PostgresClient,
        job_repo: JobRepository,
    ) -> QueueStatusResponse:
        """
        Assemble the queue snapshot from Redis depth + Postgres counts/throughput.

        Args:
            queue_introspector (QueueIntrospector): Read-only arq queue view.
            postgres (PostgresClient): Database client for the session.
            job_repo (JobRepository): Job counts + throughput source.

        Returns:
            QueueStatusResponse: Depth, per-status counts, and per-minute throughput.
        """
        # 1. Queue depth is an O(1) Redis ZCARD
        depth = await queue_introspector.queue_depth()

        # 2. Per-status counts + recent throughput come from Postgres (indexed, scalable)
        async with postgres.session() as session:
            counts = await job_repo.count_by_status(session)
            since = datetime.now(UTC) - timedelta(minutes=THROUGHPUT_WINDOW_MINUTES)
            finished = await job_repo.count_finished_since(session, since)

        # 3. Average finished jobs over the window into a per-minute rate
        return QueueStatusResponse(
            queue_depth=depth,
            counts=counts,
            throughput_per_min=round(finished / THROUGHPUT_WINDOW_MINUTES, 2),
            window_minutes=THROUGHPUT_WINDOW_MINUTES,
        )

    @classmethod
    async def build_workers(cls, *, heartbeat_reader: HeartbeatReader) -> WorkersResponse:
        """
        Assemble the live worker fleet from non-expired heartbeats.

        Args:
            heartbeat_reader (HeartbeatReader): Live worker heartbeat source.

        Returns:
            WorkersResponse: Live workers mapped to the API model.
        """
        # 1. Read live heartbeats and map each to the API model
        heartbeats = await heartbeat_reader.list_workers()
        workers = [cls.to_worker_info(hb) for hb in heartbeats]
        return WorkersResponse(workers=workers, count=len(workers))

    @classmethod
    def discovery(cls) -> MonitoringDiscoveryResponse:
        """
        Return the static descriptor of the monitoring surface for the UI tab.

        Returns:
            MonitoringDiscoveryResponse: Panels + (future) stream endpoint.
        """
        cls.logger.debug(f"Serving monitoring discovery descriptor.")
        # The stream endpoint stays None until brique C wires the SSE broadcaster.
        return MonitoringDiscoveryResponse(
            panels=[
                PanelDescriptor(
                    key="queue", title="Queue & throughput", kind="queue",
                    endpoint="/api/v1/monitoring/queue", stream=False,
                ),
                PanelDescriptor(
                    key="workers", title="Workers", kind="workers",
                    endpoint="/api/v1/monitoring/workers", stream=False,
                ),
                PanelDescriptor(
                    key="jobs", title="Jobs", kind="jobs",
                    endpoint="/api/v1/jobs", stream=False,
                ),
                PanelDescriptor(
                    key="overview", title="Overview", kind="resources",
                    endpoint="/api/v1/monitoring/overview", stream=False,
                ),
            ],
            stream_endpoint=None,
        )


# ------------------- Public API ------------------- #
__all__ = ["MonitoringHelpers", "THROUGHPUT_WINDOW_MINUTES"]
