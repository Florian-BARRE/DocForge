# ====== Code Summary ======
# GpuMetricsCollector — samples per-GPU memory/utilization via NVML (nvidia-ml-py).
# Fail-soft by design: on a CPU-only runtime (no NVIDIA driver / library), NVML init raises and
# the collector reports unavailable instead of crashing. This matches DocForge's dual GPU/CPU
# image strategy where the same image runs with or without a GPU.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
# nvidia-ml-py (module ``pynvml``) is a declared dependency, but the import is guarded so the
# SAME image boots on a CPU-only build where the wheel was not installed — consistent with the
# runtime NVMLError fall-back below and DocForge's single CPU/GPU image strategy.
try:
    import pynvml
except ImportError:  # nvidia-ml-py absent (CPU-only build) — GPU gauges disabled, not fatal.
    pynvml = None  # type: ignore[assignment]

from loggerplusplus import LoggerClass


class GpuMetricsCollector(LoggerClass):
    """
    Collects per-GPU memory and utilization gauges via NVML.

    NVML is initialized once at construction. When no GPU/driver is present (CPU-only image),
    ``nvmlInit`` raises ``NVMLError`` (LibraryNotFound / DriverNotLoaded); we catch it, mark the
    collector unavailable, and ``snapshot()`` returns ``None`` so callers degrade gracefully.
    """

    def __init__(self) -> None:
        """Initialize NVML, degrading to unavailable on CPU-only runtimes."""
        LoggerClass.__init__(self)
        self._available = False
        self._device_count = 0
        # nvidia-ml-py not installed (CPU-only build) — degrade exactly like a missing driver.
        if pynvml is None:
            self.logger.debug("nvidia-ml-py not installed; GPU gauges disabled.")
            return
        try:
            pynvml.nvmlInit()
            self._device_count = int(pynvml.nvmlDeviceGetCount())
            self._available = self._device_count > 0
            if self._available:
                self.logger.info(f"NVML ready — {self._device_count} GPU(s) visible.")
        except pynvml.NVMLError as exc:
            # CPU-only runtime or driver absent — expected, not an error.
            self.logger.debug(f"NVML unavailable ({exc}); GPU gauges disabled.")

    @property
    def available(self) -> bool:
        """Whether at least one GPU is visible through NVML."""
        return self._available

    def snapshot(self) -> list[dict[str, int]] | None:
        """
        Sample memory/utilization for every visible GPU.

        Returns:
            list[dict] | None: One entry per GPU (``index, mem_used_mb, mem_total_mb,
            util_gpu_pct``), or ``None`` when no GPU is available.
        """
        # 1. Short-circuit on CPU-only runtimes
        if not self._available:
            return None

        # 2. Sample each visible GPU; a per-device NVML error degrades that device to None-skip
        gauges: list[dict[str, int]] = []
        for index in range(self._device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gauges.append({
                    "index": index,
                    "mem_used_mb": int(mem.used // 1024**2),
                    "mem_total_mb": int(mem.total // 1024**2),
                    "util_gpu_pct": int(util.gpu),
                })
            except pynvml.NVMLError as exc:
                self.logger.warning(f"NVML read failed for GPU {index} ({exc}); skipping.")
        return gauges or None


# ------------------- Public API ------------------- #
__all__ = ["GpuMetricsCollector"]
