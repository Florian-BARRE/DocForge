# ====== Code Summary ======
# /api/v1/monitoring router (Brique A) — queue status, worker fleet, an aggregate overview, and
# the discovery descriptor for the UI. All snapshots are read-only: queue depth from Redis, job
# counts/throughput from Postgres, worker gauges from heartbeats. The multi-source assembly lives
# in MonitoringHelpers; routes only wire CONTEXT services into it. Real-time SSE is brique C.

# ====== Standard Library Imports ======
from __future__ import annotations

from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

# ====== Internal Project Imports ======
from ...context import CONTEXT
from ...libs.utils.error_handling import auto_handle_errors
from ...libs.utils.sse import SseHelpers
from .helpers import MonitoringHelpers
from .models import (
    MonitoringDiscoveryResponse,
    OverviewResponse,
    QueueStatusResponse,
    ResourcesResponse,
    WorkersResponse,
)

router = APIRouter(tags=["monitoring"])


@router.get("/queue", response_model=QueueStatusResponse)
@auto_handle_errors
async def get_queue() -> QueueStatusResponse:
    """
    Return queue depth, per-status job counts, and recent throughput.

    Returns:
        QueueStatusResponse: The queue snapshot.
    """
    # 1. Assemble from the injected services
    return await MonitoringHelpers.build_queue_status(
        queue_introspector=CONTEXT.queue_introspector,
        postgres=CONTEXT.postgres,
        job_repo=CONTEXT.job_repo,
    )


@router.get("/workers", response_model=WorkersResponse)
@auto_handle_errors
async def get_workers() -> WorkersResponse:
    """
    Return the live worker fleet with per-worker load/resource gauges.

    Returns:
        WorkersResponse: Live workers (dead workers drop out via heartbeat TTL).
    """
    # 1. Assemble from the live heartbeats
    return await MonitoringHelpers.build_workers(heartbeat_reader=CONTEXT.heartbeat_reader)


@router.get("/overview", response_model=OverviewResponse)
@auto_handle_errors
async def get_overview() -> OverviewResponse:
    """
    Return an aggregate snapshot (queue + workers) for the dashboard.

    Returns:
        OverviewResponse: Combined queue and worker snapshots with a timestamp.
    """
    # 1. Assemble both sub-snapshots and stamp the generation time
    queue = await MonitoringHelpers.build_queue_status(
        queue_introspector=CONTEXT.queue_introspector,
        postgres=CONTEXT.postgres,
        job_repo=CONTEXT.job_repo,
    )
    workers = await MonitoringHelpers.build_workers(heartbeat_reader=CONTEXT.heartbeat_reader)
    return OverviewResponse(
        queue=queue,
        workers=workers,
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get("/resources", response_model=ResourcesResponse)
@auto_handle_errors
async def get_resources() -> ResourcesResponse:
    """
    Return the resource snapshot: device gauge + admission limits + live load (Brique D).

    Returns:
        ResourcesResponse: Device resolution, global admission thresholds, queue depth, counts.
    """
    # 1. Assemble device gauge + limits + live counts from the injected services
    return await MonitoringHelpers.build_resources(
        device_manager=CONTEXT.device_manager,
        queue_introspector=CONTEXT.queue_introspector,
        postgres=CONTEXT.postgres,
        job_repo=CONTEXT.job_repo,
        runtime_config=CONTEXT.RUNTIME_CONFIG,
    )


# NOTE: SSE route — returns an EventSourceResponse stream, so it intentionally has NO
# response_model (a live stream cannot be described by a Pydantic model). @auto_handle_errors still
# guards exceptions raised while building the response; errors inside the stream are handled by the
# generator itself (it always unsubscribes in its finally block).
@router.get("/stream")
@auto_handle_errors
async def stream_events() -> EventSourceResponse:
    """
    Stream every monitoring event (jobs, stages, workers, batches) as Server-Sent Events.

    Returns:
        EventSourceResponse: Unfiltered live event stream for the monitoring dashboard.
    """
    # 1. Fan out the global event bus to this client (no predicate = all events)
    return SseHelpers.stream(
        CONTEXT.event_broadcaster,
        keepalive=CONTEXT.RUNTIME_CONFIG.SSE_KEEPALIVE_SECONDS,
    )


@router.get("/discovery", response_model=MonitoringDiscoveryResponse)
@auto_handle_errors
async def get_discovery() -> MonitoringDiscoveryResponse:
    """
    Return the discovery descriptor that drives the monitoring UI tab.

    Returns:
        MonitoringDiscoveryResponse: Panel descriptors + (future) stream endpoint.
    """
    # 1. Static descriptor — the UI builds the Monitoring tab from this
    return MonitoringHelpers.discovery()
