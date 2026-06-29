# ====== Code Summary ======
# Unit tests for DeviceManager.snapshot() (Brique D): the read-only gauge that feeds the monitoring
# "resources" panel. Verifies CPU-only resolution (no GPU detected), GPU resolution when a GPU is
# present, and that VLM (which intentionally skips CPU) falls back to remote on a CPU-only host.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from common_libs.providers.device import DeviceSnapshot
from common_libs.pipeline.bricks.providers.device.manager import DeviceManager


class TestDeviceSnapshot:
    """snapshot() reports availability + the device each capability currently resolves to."""

    def test_cpu_only_host_resolves_capabilities(self) -> None:
        """With no GPU detected, every capability resolves to a non-GPU device."""
        # 1. A freshly constructed manager has not detected a GPU
        manager = DeviceManager()
        snap = manager.snapshot()

        # 2. It is a frozen gauge reporting CPU-only state for all six capabilities
        assert isinstance(snap, DeviceSnapshot)
        assert snap.gpu_available is False
        assert snap.gpu_name is None
        assert set(snap.capabilities) == {"parse", "ocr", "vlm", "embed", "rerank", "classify"}
        assert "gpu" not in snap.capabilities.values()

    def test_vlm_falls_back_to_remote_without_gpu(self) -> None:
        """VLM skips CPU by design, so on a CPU-only host it resolves to remote."""
        manager = DeviceManager()
        snap = manager.snapshot()
        assert snap.capabilities["vlm"] == "remote"
        assert snap.capabilities["embed"] == "cpu"

    def test_reports_gpu_when_available(self) -> None:
        """When a GPU is detected, the gauge reflects it and capabilities resolve to gpu."""
        # 1. Simulate a detected GPU without importing torch
        manager = DeviceManager()
        manager._gpu_available = True
        manager._gpu_name = "Tesla V100-SXM2-32GB"
        manager._cuda_version = "11.8"

        # 2. The snapshot surfaces the GPU and resolves capabilities to it
        snap = manager.snapshot()
        assert snap.gpu_available is True
        assert snap.gpu_name == "Tesla V100-SXM2-32GB"
        assert snap.cuda_version == "11.8"
        assert snap.capabilities["embed"] == "gpu"
        assert snap.capabilities["vlm"] == "gpu"
