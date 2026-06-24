# ====== Code Summary ======
# Pydantic response models for the /api/v1/monitoring router (Brique A): queue status,
# worker fleet, an aggregate overview, and the discovery descriptor that drives the UI tab.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class GpuGauge(BaseModel):
    """Per-GPU memory/utilization gauge."""

    index: int = Field(..., description="GPU index.")
    mem_used_mb: int = Field(..., description="Used GPU memory (MB).")
    mem_total_mb: int = Field(..., description="Total GPU memory (MB).")
    util_gpu_pct: int = Field(..., description="GPU utilization percent.")


class WorkerInfo(BaseModel):
    """Live snapshot of one worker process."""

    worker_id: str = Field(..., description="Stable worker id (hostname:pid:rand).")
    hostname: str = Field(..., description="Host the worker runs on.")
    pid: int = Field(..., description="OS process id.")
    started_at: str = Field(..., description="ISO-8601 worker start time.")
    last_seen: str = Field(..., description="ISO-8601 last heartbeat time.")
    status: str = Field(..., description="idle | busy.")
    current_job_id: str | None = Field(None, description="Job currently executing.")
    jobs_processed: int = Field(0, description="Jobs completed since startup.")
    cpu_pct: float = Field(0.0, description="Process CPU percent.")
    rss_mb: float = Field(0.0, description="Process resident memory (MB).")
    sys_cpu_pct: float = Field(0.0, description="Host CPU percent.")
    sys_ram_pct: float = Field(0.0, description="Host RAM used percent.")
    gpu: list[GpuGauge] = Field(default_factory=list, description="Per-GPU gauges.")


class QueueStatusResponse(BaseModel):
    """Queue depth, per-status job counts, and recent throughput."""

    queue_depth: int = Field(..., description="Pending jobs in the arq queue.")
    counts: dict[str, int] = Field(..., description="Job counts per status (Postgres).")
    throughput_per_min: float = Field(..., description="Jobs finished per minute (recent window).")
    window_minutes: int = Field(..., description="Throughput averaging window (minutes).")


class WorkersResponse(BaseModel):
    """The live worker fleet."""

    workers: list[WorkerInfo] = Field(..., description="Live workers (non-expired heartbeats).")
    count: int = Field(..., description="Number of live workers.")


class OverviewResponse(BaseModel):
    """Aggregate monitoring snapshot for the dashboard."""

    queue: QueueStatusResponse = Field(..., description="Queue + throughput snapshot.")
    workers: WorkersResponse = Field(..., description="Worker fleet snapshot.")
    generated_at: str = Field(..., description="ISO-8601 time the snapshot was assembled.")


class DeviceSnapshotModel(BaseModel):
    """Read-only gauge of the device manager's current resolution state (Brique D)."""

    gpu_available: bool = Field(..., description="Whether a CUDA GPU was detected at startup.")
    gpu_name: str | None = Field(None, description="Detected GPU device name (null on CPU-only).")
    cuda_version: str | None = Field(None, description="Detected CUDA toolkit version (null on CPU-only).")
    capabilities: dict[str, str] = Field(
        ..., description="Capability → device it currently resolves to (e.g. {'vlm': 'remote'})."
    )


class AdmissionLimitsModel(BaseModel):
    """Deployment-global resource-admission thresholds (0 = unlimited)."""

    enabled: bool = Field(..., description="Whether the resource gate is active.")
    max_queue_depth: int = Field(..., description="Backlog cap (0 = unlimited).")
    max_in_flight_global: int = Field(..., description="Global running-jobs cap (0 = unlimited).")


class ResourcesResponse(BaseModel):
    """Resource snapshot: device gauge + admission limits + live load (Brique D)."""

    device: DeviceSnapshotModel = Field(..., description="Device resolution gauge.")
    limits: AdmissionLimitsModel = Field(..., description="Global admission thresholds.")
    queue_depth: int = Field(..., description="Pending jobs in the arq queue.")
    running: int = Field(..., description="Jobs currently running (all collections).")
    counts: dict[str, int] = Field(..., description="Job counts per status (Postgres).")
    generated_at: str = Field(..., description="ISO-8601 time the snapshot was assembled.")


class PanelDescriptor(BaseModel):
    """Descriptor for one monitoring panel, consumed by the discovery-driven UI tab."""

    key: str = Field(..., description="Stable panel key.")
    title: str = Field(..., description="Human-readable panel title.")
    kind: str = Field(..., description="Render hint (queue|workers|jobs|resources).")
    endpoint: str = Field(..., description="REST endpoint backing this panel.")
    stream: bool = Field(False, description="Whether a live SSE stream backs it (brique C).")


class MonitoringDiscoveryResponse(BaseModel):
    """Self-description of the monitoring surface for the UI."""

    panels: list[PanelDescriptor] = Field(..., description="Available monitoring panels.")
    stream_endpoint: str | None = Field(
        None, description="Global SSE stream endpoint (None until brique C lands)."
    )


# ------------------- Public API ------------------- #
__all__ = [
    "GpuGauge",
    "WorkerInfo",
    "QueueStatusResponse",
    "WorkersResponse",
    "OverviewResponse",
    "DeviceSnapshotModel",
    "AdmissionLimitsModel",
    "ResourcesResponse",
    "PanelDescriptor",
    "MonitoringDiscoveryResponse",
]
