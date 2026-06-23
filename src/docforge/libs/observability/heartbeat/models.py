# ====== Code Summary ======
# WorkerHeartbeat — the snapshot a worker process writes to Redis on every heartbeat tick and
# the monitoring layer reads back. Plain data carrier (dataclass), JSON-serializable for Redis.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Redis key prefix for worker heartbeats. One key per worker, with a TTL so a dead worker's key
# expires on its own (no explicit cleanup needed).
WORKER_KEY_PREFIX: str = "docforge:worker:"


@dataclass(slots=True)
class WorkerHeartbeat:
    """
    Liveness + load snapshot for a single worker process.

    Written under ``docforge:worker:{worker_id}`` with a TTL. ``gpu`` mirrors the GPU gauge list
    from the metrics collector (absent/empty on CPU-only runtimes).

    Attributes:
        worker_id (str): Stable per-process id (``hostname:pid:rand``).
        hostname (str): Host the worker runs on.
        pid (int): OS process id.
        started_at (str): ISO-8601 worker start time.
        last_seen (str): ISO-8601 timestamp of this heartbeat.
        status (str): ``idle`` or ``busy``.
        current_job_id (str | None): Job currently executing, if any.
        jobs_processed (int): Count of jobs completed by this worker since startup.
        cpu_pct (float): Process CPU percent at sample time.
        rss_mb (float): Process resident memory (MB) at sample time.
        sys_cpu_pct (float): Host CPU percent.
        sys_ram_pct (float): Host RAM used percent.
        gpu (list): Per-GPU gauges (``index, mem_used_mb, mem_total_mb, util_gpu_pct``).
    """

    worker_id: str
    hostname: str
    pid: int
    started_at: str
    last_seen: str
    status: str = "idle"
    current_job_id: str | None = None
    jobs_processed: int = 0
    cpu_pct: float = 0.0
    rss_mb: float = 0.0
    sys_cpu_pct: float = 0.0
    sys_ram_pct: float = 0.0
    gpu: list[dict[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerHeartbeat:
        """
        Rebuild a heartbeat from a parsed dict, ignoring unknown keys.

        Args:
            data (dict): Parsed JSON payload read back from Redis.

        Returns:
            WorkerHeartbeat: Reconstructed instance.
        """
        # Only keep known fields so a forward-compatible payload never breaks the reader.
        allowed = {f for f in cls.__slots__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})


# ------------------- Public API ------------------- #
__all__ = ["WorkerHeartbeat", "WORKER_KEY_PREFIX"]
