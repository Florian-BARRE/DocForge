# ====== Code Summary ======
# DeviceManager — centralized GPU/CPU detection + per-capability resolution, app-local.
#
# The node-engine rewrite (common_libs.pipelines.*) dropped the shared DeviceManager: the worker
# resolves device concerns inside its providers now and no longer needs a central allocator. The
# FastAPI app, however, STILL surfaces device state on two read-only endpoints (GET /health gpu_*
# and GET /monitoring/resources device gauge), so the manager lives here as an app-dedicated
# infrastructure handle. It depends ONLY on the surviving value-contracts (Device / DeviceCapability
# enums + DeviceSnapshot) still published by common_libs.providers.device — no pipelines import.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Literal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.providers.device.enums import Device, DeviceCapability
from common_libs.providers.device.snapshot import DeviceSnapshot


class DeviceManager(LoggerClass):
    """
    Centralized device detector and allocator for the FastAPI app.

    Responsibilities:
    - Detect GPU availability (CUDA) once at startup (called from the lifespan).
    - Expose ``resolve(capability, preferred_chain)`` to pick the best available device for a
      capability, respecting the preferred fallback order.
    - Expose ``gpu_available`` / ``gpu_name`` for the simple /health gauge and ``snapshot()`` for
      the /monitoring/resources read-only device panel.

    The default resolution order per capability (spec §6.2):
        embed    → [gpu, cpu, remote]   (CPU viable for BGE-M3 ONNX)
        parse    → [gpu, cpu, remote]   (Docling CPU OK, slower)
        ocr      → [gpu, cpu, remote]   (PaddleOCR / Tesseract on CPU)
        vlm      → [gpu, remote]        (CPU skipped: quality/latency unacceptable in volume)
        rerank   → [gpu, cpu, remote]
        classify → [gpu, cpu]           (small ViT, ONNX CPU OK)
    """

    # Default fallback chains per capability.
    _DEFAULT_CHAINS: dict[DeviceCapability, list[Device]] = {
        DeviceCapability.PARSE: [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.OCR: [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.VLM: [Device.GPU, Device.REMOTE],  # CPU intentionally skipped
        DeviceCapability.EMBED: [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.RERANK: [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.CLASSIFY: [Device.GPU, Device.CPU],
    }

    def __init__(self) -> None:
        """Initialize the manager in the undetected, CPU-only default state."""
        LoggerClass.__init__(self)
        self._gpu_available: bool = False
        self._gpu_name: str | None = None
        self._cuda_version: str | None = None
        self._detected: bool = False

    def __repr__(self) -> str:
        status = f"GPU={self._gpu_name}" if self._gpu_available else "CPU-only"
        return f"DeviceManager({status})"

    @property
    def gpu_available(self) -> bool:
        """True if a CUDA GPU was detected at startup."""
        return self._gpu_available

    @property
    def gpu_name(self) -> str | None:
        """Detected GPU device name (e.g. 'Tesla V100-SXM2-32GB'), or None on CPU-only hosts."""
        return self._gpu_name

    def detect(self) -> None:
        """
        Probe GPU availability via torch.cuda — called once at startup (in the lifespan).

        Safe when torch is absent (the app image is CPU-only): it falls back to CPU-only mode
        gracefully instead of raising.
        """
        # 1. Attempt to import torch (an optional dependency, absent on the light app image).
        try:
            import torch  # type: ignore[import-untyped]

            self._gpu_available = torch.cuda.is_available()
            if self._gpu_available:
                self._gpu_name = torch.cuda.get_device_name(0)
                self._cuda_version = torch.version.cuda or "unknown"
        except ImportError:
            # torch not installed → CPU-only mode.
            self._gpu_available = False

        # 2. Log the detection outcome.
        if self._gpu_available:
            self.logger.info(f"GPU detected: {self._gpu_name} (CUDA {self._cuda_version})")
        else:
            self.logger.warning(f"No GPU available — all workloads will use CPU or remote API.")

        self._detected = True

    def resolve(
        self,
        capability: DeviceCapability,
        preferred_chain: list[Literal["gpu", "cpu", "remote"]] | None = None,
    ) -> Device:
        """
        Return the best available device for a capability.

        Args:
            capability (DeviceCapability): The ML capability being resolved.
            preferred_chain (list | None): Ordered preference list; None → the capability default.

        Returns:
            Device: The first available device in the preference chain.

        Raises:
            RuntimeError: When no device in the chain is available.
        """
        # 1. Build the effective preference chain (explicit override, else the capability default).
        chain: list[Device] = (
            [Device(d) for d in preferred_chain]
            if preferred_chain
            else self._DEFAULT_CHAINS.get(capability, [Device.CPU, Device.REMOTE])
        )

        # 2. Walk the chain and return the first available device (skip GPU when absent).
        for device in chain:
            if device == Device.GPU and not self._gpu_available:
                continue
            return device

        raise RuntimeError(
            f"No available device for capability={capability!r}. Chain exhausted: {chain}."
        )

    def snapshot(self) -> DeviceSnapshot:
        """
        Return a read-only gauge of the current resolution state (monitoring /resources panel).

        Reports GPU availability plus, for each known capability, the device it would currently
        resolve to via the default chain. Best-effort: a capability whose chain is exhausted is
        reported as ``"unavailable"`` rather than raising.

        Returns:
            DeviceSnapshot: Immutable view of availability + per-capability device.
        """
        # 1. Resolve each capability against its default chain (never raises here).
        capabilities: dict[str, str] = {}
        for capability in DeviceCapability:
            try:
                capabilities[capability.value] = self.resolve(capability).value
            except RuntimeError:
                capabilities[capability.value] = "unavailable"

        # 2. Pack availability + the per-capability mapping into the immutable gauge.
        return DeviceSnapshot(
            gpu_available=self._gpu_available,
            gpu_name=self._gpu_name,
            cuda_version=self._cuda_version,
            capabilities=capabilities,
        )


__all__ = ["DeviceManager"]
