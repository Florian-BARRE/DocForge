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
from common_libs.observability.heartbeat import WorkerHeartbeat

# ====== Local Project Imports ======
from .models import (
    AdmissionLimitsModel,
    DeviceSnapshotModel,
    MonitoringDiscoveryResponse,
    PanelDescriptor,
    QueueStatusResponse,
    ResourcesResponse,
    WorkerInfo,
    WorkersResponse,
)

if TYPE_CHECKING:
    from config import RUNTIME_CONFIG
    from common_libs.observability.heartbeat import HeartbeatReader
    from libs.observability.queue import QueueIntrospector
    from common_libs.providers.device_manager import DeviceManager
    from common_libs.storage.postgres.client import PostgresClient
    from common_libs.storage.postgres.repositories import JobRepository

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
    async def build_resources(
        cls,
        *,
        device_manager: DeviceManager,
        queue_introspector: QueueIntrospector,
        postgres: PostgresClient,
        job_repo: JobRepository,
        runtime_config: type[RUNTIME_CONFIG],
    ) -> ResourcesResponse:
        """
        Assemble the resource snapshot: device gauge + admission limits + live load (Brique D).

        Args:
            device_manager (DeviceManager): Source of the read-only device gauge.
            queue_introspector (QueueIntrospector): Read-only arq backlog depth.
            postgres (PostgresClient): Database client for the session.
            job_repo (JobRepository): Per-status job counts.
            runtime_config (type[RUNTIME_CONFIG]): Carries the global admission thresholds.

        Returns:
            ResourcesResponse: Device + limits + queue depth + running/per-status counts.
        """
        # 1. Read-only device gauge (no allocation logic exposed)
        snap = device_manager.snapshot()

        # 2. Backlog depth (Redis ZCARD) + per-status counts (indexed Postgres)
        depth = await queue_introspector.queue_depth()
        async with postgres.session() as session:
            counts = await job_repo.count_by_status(session)

        # 3. Pack device + global limits + live load into the response
        return ResourcesResponse(
            device=DeviceSnapshotModel(
                gpu_available=snap.gpu_available,
                gpu_name=snap.gpu_name,
                cuda_version=snap.cuda_version,
                capabilities=snap.capabilities,
            ),
            limits=AdmissionLimitsModel(
                enabled=runtime_config.ADMISSION_ENABLED,
                max_queue_depth=runtime_config.ADMISSION_MAX_QUEUE_DEPTH,
                max_in_flight_global=runtime_config.ADMISSION_MAX_IN_FLIGHT_GLOBAL,
            ),
            queue_depth=depth,
            running=counts.get("running", 0),
            counts=counts,
            generated_at=datetime.now(UTC).isoformat(),
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
        # Brique C wired the SSE broadcaster: queue/workers panels now have a live backing stream,
        # and the global stream endpoint is advertised for the UI to open one EventSource.
        return MonitoringDiscoveryResponse(
            panels=[
                PanelDescriptor(
                    key="queue", title="Queue & throughput", kind="queue",
                    endpoint="/api/v1/monitoring/queue", stream=True,
                ),
                PanelDescriptor(
                    key="workers", title="Workers", kind="workers",
                    endpoint="/api/v1/monitoring/workers", stream=True,
                ),
                PanelDescriptor(
                    key="jobs", title="Jobs", kind="jobs",
                    endpoint="/api/v1/jobs", stream=True,
                ),
                PanelDescriptor(
                    key="overview", title="Overview", kind="resources",
                    endpoint="/api/v1/monitoring/overview", stream=True,
                ),
                PanelDescriptor(
                    key="resources", title="Resources", kind="resources",
                    endpoint="/api/v1/monitoring/resources", stream=False,
                ),
            ],
            stream_endpoint="/api/v1/monitoring/stream",
        )


# ------------------- Public API ------------------- #
__all__ = ["MonitoringHelpers", "THROUGHPUT_WINDOW_MINUTES"]
