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

# ====== Internal Project Imports ======
from ...context import CONTEXT
from ...libs.utils.error_handling import auto_handle_errors
from .helpers import MonitoringHelpers
from .models import (
    MonitoringDiscoveryResponse,
    OverviewResponse,
    QueueStatusResponse,
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
