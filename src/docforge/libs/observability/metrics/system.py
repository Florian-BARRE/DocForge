# ====== Code Summary ======
# SystemMetricsCollector — samples CPU and memory gauges for the current process and the host
# via psutil. Warms psutil's per-process CPU counter at construction so the first real sample
# is meaningful (psutil's first cpu_percent() call always returns 0.0).

# ====== Standard Library Imports ======
from __future__ import annotations

import os

# ====== Third-Party Library Imports ======
import psutil
from loggerplusplus import LoggerClass


class SystemMetricsCollector(LoggerClass):
    """
    Collects CPU / memory gauges for the running process and the host.

    One instance per process (worker or backend). Construction performs the mandatory psutil
    warm-up call so subsequent ``snapshot()`` results are accurate deltas, never the initial 0.0.
    """

    def __init__(self) -> None:
        """Initialize the collector and warm up the per-process CPU counter."""
        LoggerClass.__init__(self)
        self._proc = psutil.Process(os.getpid())
        # Warm-up: psutil's first cpu_percent() returns a meaningless 0.0 by design — discard it
        # here so the first real snapshot reports a true delta.
        self._proc.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)

    def snapshot(self) -> dict[str, float]:
        """
        Sample current CPU / memory gauges.

        Returns:
            dict[str, float]: ``cpu_pct`` (this process), ``rss_mb`` (this process resident set),
            ``sys_cpu_pct`` (host CPU), ``sys_ram_pct`` (host RAM used percent).
        """
        # 1. Per-process gauges (non-blocking; accurate after the construction warm-up)
        cpu_pct = float(self._proc.cpu_percent(interval=None))
        rss_mb = round(self._proc.memory_info().rss / 1024**2, 1)

        # 2. Host-wide gauges
        sys_cpu_pct = float(psutil.cpu_percent(interval=None))
        sys_ram_pct = float(psutil.virtual_memory().percent)

        return {
            "cpu_pct": cpu_pct,
            "rss_mb": rss_mb,
            "sys_cpu_pct": sys_cpu_pct,
            "sys_ram_pct": sys_ram_pct,
        }


# ------------------- Public API ------------------- #
__all__ = ["SystemMetricsCollector"]
