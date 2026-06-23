# ====== Code Summary ======
# Unit tests for the metrics collectors: system gauges shape, GPU fail-soft on CPU-only runtimes,
# and the composed collector's enabled/disabled behaviour.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
import libs.observability.metrics.gpu as gpu_mod
from libs.observability.metrics import GpuMetricsCollector, MetricsCollector, SystemMetricsCollector


class TestSystemMetrics:
    """SystemMetricsCollector.snapshot"""

    def test_snapshot_has_expected_keys_and_types(self) -> None:
        """Snapshot exposes process + host gauges as floats."""
        snap = SystemMetricsCollector().snapshot()
        for key in ("cpu_pct", "rss_mb", "sys_cpu_pct", "sys_ram_pct"):
            assert key in snap
            assert isinstance(snap[key], float)
        assert snap["rss_mb"] > 0  # the test process holds some resident memory


class TestGpuFailSoft:
    """GpuMetricsCollector degrades gracefully without a GPU."""

    def test_unavailable_when_nvml_init_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A CPU-only runtime (nvmlInit raises NVMLError) → unavailable + None snapshot."""
        def _raise() -> None:
            raise gpu_mod.pynvml.NVMLError(gpu_mod.pynvml.NVML_ERROR_LIBRARY_NOT_FOUND)

        monkeypatch.setattr(gpu_mod.pynvml, "nvmlInit", _raise)
        collector = GpuMetricsCollector()
        assert collector.available is False
        assert collector.snapshot() is None


class TestMetricsCollector:
    """MetricsCollector composition + enabled flag."""

    def test_disabled_returns_empty_snapshot(self) -> None:
        """When disabled, no sampling occurs and snapshot is empty."""
        assert MetricsCollector(enabled=False).snapshot() == {}

    def test_enabled_includes_system_gauges(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When enabled on a CPU-only runtime, system gauges are present and gpu is absent."""
        # Force the GPU side to be unavailable so the test is host-agnostic.
        def _raise() -> None:
            raise gpu_mod.pynvml.NVMLError(gpu_mod.pynvml.NVML_ERROR_LIBRARY_NOT_FOUND)

        monkeypatch.setattr(gpu_mod.pynvml, "nvmlInit", _raise)
        snap = MetricsCollector(enabled=True).snapshot()
        assert "cpu_pct" in snap
        assert "gpu" not in snap
