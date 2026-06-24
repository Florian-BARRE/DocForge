# ====== Code Summary ======
# API tests for the /api/v1/monitoring router: queue snapshot + throughput, worker fleet,
# aggregate overview, and the discovery descriptor.

# ====== Standard Library Imports ======
from __future__ import annotations

from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from libs.observability.heartbeat import WorkerHeartbeat
from libs.providers.device import DeviceSnapshot


def _heartbeat() -> WorkerHeartbeat:
    return WorkerHeartbeat(
        worker_id="host:1:abcd", hostname="host", pid=1,
        started_at="2026-06-23T00:00:00+00:00", last_seen="2026-06-23T00:00:05+00:00",
        status="busy", current_job_id="job-1", jobs_processed=2, cpu_pct=10.0, rss_mb=128.0,
    )


class TestQueue:
    """GET /api/v1/monitoring/queue"""

    @pytest.mark.asyncio
    async def test_queue_snapshot_with_throughput(self, client: httpx.AsyncClient) -> None:
        """Queue endpoint returns depth, counts, and a per-minute throughput over the window."""
        CONTEXT.queue_introspector.queue_depth = AsyncMock(return_value=3)
        CONTEXT.job_repo.count_by_status = AsyncMock(return_value={"running": 2, "done": 5})
        CONTEXT.job_repo.count_finished_since = AsyncMock(return_value=10)

        response = await client.get("/api/v1/monitoring/queue")
        assert response.status_code == 200
        body = response.json()
        assert body["queue_depth"] == 3
        assert body["counts"] == {"running": 2, "done": 5}
        # 10 finished over a 5-minute window → 2.0 jobs/min
        assert body["throughput_per_min"] == 2.0
        assert body["window_minutes"] == 5


class TestWorkers:
    """GET /api/v1/monitoring/workers"""

    @pytest.mark.asyncio
    async def test_lists_live_workers(self, client: httpx.AsyncClient) -> None:
        """Worker endpoint maps live heartbeats to worker info."""
        CONTEXT.heartbeat_reader.list_workers = AsyncMock(return_value=[_heartbeat()])
        response = await client.get("/api/v1/monitoring/workers")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["workers"][0]["worker_id"] == "host:1:abcd"
        assert body["workers"][0]["status"] == "busy"


class TestOverview:
    """GET /api/v1/monitoring/overview"""

    @pytest.mark.asyncio
    async def test_overview_combines_queue_and_workers(self, client: httpx.AsyncClient) -> None:
        """Overview aggregates the queue + worker snapshots with a timestamp."""
        CONTEXT.queue_introspector.queue_depth = AsyncMock(return_value=0)
        CONTEXT.job_repo.count_by_status = AsyncMock(return_value={})
        CONTEXT.job_repo.count_finished_since = AsyncMock(return_value=0)
        CONTEXT.heartbeat_reader.list_workers = AsyncMock(return_value=[_heartbeat()])

        response = await client.get("/api/v1/monitoring/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["workers"]["count"] == 1
        assert "generated_at" in body
        assert body["queue"]["queue_depth"] == 0


class TestResources:
    """GET /api/v1/monitoring/resources"""

    @pytest.mark.asyncio
    async def test_resources_snapshot(self, client: httpx.AsyncClient) -> None:
        """Resources endpoint returns the device gauge, admission limits, and live load (Brique D)."""
        CONTEXT.device_manager.snapshot = lambda: DeviceSnapshot(
            gpu_available=False, gpu_name=None, cuda_version=None,
            capabilities={"vlm": "remote", "embed": "cpu"},
        )
        CONTEXT.queue_introspector.queue_depth = AsyncMock(return_value=4)
        CONTEXT.job_repo.count_by_status = AsyncMock(return_value={"running": 2, "pending": 1})
        CONTEXT.RUNTIME_CONFIG.ADMISSION_ENABLED = True
        CONTEXT.RUNTIME_CONFIG.ADMISSION_MAX_QUEUE_DEPTH = 0
        CONTEXT.RUNTIME_CONFIG.ADMISSION_MAX_IN_FLIGHT_GLOBAL = 0

        response = await client.get("/api/v1/monitoring/resources")
        assert response.status_code == 200
        body = response.json()
        assert body["device"]["gpu_available"] is False
        assert body["device"]["capabilities"]["vlm"] == "remote"
        assert body["limits"]["enabled"] is True
        assert body["queue_depth"] == 4
        assert body["running"] == 2
        assert body["counts"] == {"running": 2, "pending": 1}


class TestDiscovery:
    """GET /api/v1/monitoring/discovery"""

    @pytest.mark.asyncio
    async def test_discovery_lists_panels(self, client: httpx.AsyncClient) -> None:
        """Discovery exposes the monitoring panels for the UI tab."""
        response = await client.get("/api/v1/monitoring/discovery")
        assert response.status_code == 200
        body = response.json()
        keys = {p["key"] for p in body["panels"]}
        assert {"queue", "workers", "jobs", "overview", "resources"} <= keys
        # Brique C wired the SSE broadcaster: the global stream endpoint is now advertised.
        assert body["stream_endpoint"] == "/api/v1/monitoring/stream"
