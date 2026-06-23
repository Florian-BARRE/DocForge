# ====== Code Summary ======
# MetricsCollector — composes the system (psutil) and GPU (NVML) collectors into a single
# resource snapshot. Honours an ``enabled`` flag (OBS_METRICS_ENABLED) so gauge sampling can be
# turned off entirely without removing the wiring.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .gpu import GpuMetricsCollector
from .system import SystemMetricsCollector


class MetricsCollector(LoggerClass):
    """
    Aggregates host/process and GPU gauges into one resource snapshot.

    A single instance lives per process. When disabled, ``snapshot()`` returns an empty dict so
    heartbeat payloads stay small and no sampling cost is paid.
    """

    def __init__(self, enabled: bool = True) -> None:
        """
        Initialize the composed collectors.

        Args:
            enabled (bool): When False, skip all sampling (``snapshot()`` returns ``{}``).
        """
        LoggerClass.__init__(self)
        self._enabled = enabled
        # Collectors are constructed even when disabled is False so the warm-up/NVML init happens
        # once up-front; sampling is gated per call by the ``enabled`` flag.
        self._system = SystemMetricsCollector() if enabled else None
        self._gpu = GpuMetricsCollector() if enabled else None

    def snapshot(self) -> dict[str, object]:
        """
        Return a combined resource snapshot.

        Returns:
            dict[str, object]: ``{}`` when disabled, else system gauges plus an optional
            ``gpu`` list (absent when no GPU is available).
        """
        # 1. Disabled → empty snapshot
        if not self._enabled or self._system is None:
            return {}

        # 2. System gauges always present; GPU gauges only when a device is visible
        snapshot: dict[str, object] = dict(self._system.snapshot())
        gpu = self._gpu.snapshot() if self._gpu is not None else None
        if gpu is not None:
            snapshot["gpu"] = gpu
        return snapshot


# ------------------- Public API ------------------- #
__all__ = ["MetricsCollector"]
