# ====== Code Summary ======
# Centralized GPU/CPU device detection and allocation.
# No individual provider contains device-selection logic — they declare preferences,
# DeviceManager resolves them.  Supports CUDA 11.8 (V100 Tesla) and CPU-only modes.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Literal

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .enums import Device, DeviceCapability
from .snapshot import DeviceSnapshot


class DeviceManager:
    """
    Centralized device detector and allocator.

    Responsibilities:
    - Detect GPU availability (CUDA) at startup — once, not per-call.
    - Expose ``resolve(capability, preferred_chain)`` to pick the best available device
      for each capability, respecting the preferred fallback order from the provider spec.
    - Expose ``device`` property for simple GPU/CPU checks.

    The resolution order per capability (from spec §6.2):
        embed   → [gpu, cpu, remote]  (CPU viable for BGE-M3 ONNX)
        parse   → [gpu, cpu, remote]  (Docling CPU OK, slower)
        ocr     → [gpu, cpu, remote]  (PaddleOCR or Tesseract on CPU)
        vlm     → [gpu, remote]       (CPU skipped: quality/latency unacceptable in volume)
        rerank  → [gpu, cpu, remote]
        classify → [gpu, cpu]         (small ViT, ONNX CPU OK)
    """

    logger = loggerplusplus.bind(identifier="DeviceManager")

    # Default fallback chains per capability (overridable via collection config)
    _DEFAULT_CHAINS: dict[DeviceCapability, list[Device]] = {
        DeviceCapability.PARSE:    [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.OCR:      [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.VLM:      [Device.GPU, Device.REMOTE],  # CPU intentionally skipped
        DeviceCapability.EMBED:    [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.RERANK:   [Device.GPU, Device.CPU, Device.REMOTE],
        DeviceCapability.CLASSIFY: [Device.GPU, Device.CPU],
    }

    def __init__(self) -> None:
        self._gpu_available: bool = False
        self._gpu_name: str | None = None
        self._cuda_version: str | None = None
        self._detected: bool = False

    def __repr__(self) -> str:
        status = f"GPU={self._gpu_name}" if self._gpu_available else "CPU-only"
        return f"DeviceManager({status})"

    def detect(self) -> None:
        """
        Probe GPU availability via torch.cuda.

        Called once at startup (in lifespan).  Safe to call if torch is not installed —
        falls back to CPU-only mode gracefully.
        """
        # 1. Attempt to import torch (optional dependency)
        try:
            import torch  # type: ignore[import-untyped]

            self._gpu_available = torch.cuda.is_available()
            if self._gpu_available:
                self._gpu_name = torch.cuda.get_device_name(0)
                self._cuda_version = torch.version.cuda or "unknown"
        except ImportError:
            # torch not installed → CPU-only mode
            self._gpu_available = False

        # 2. Log detection result
        if self._gpu_available:
            self.logger.info(
                f"GPU detected: {self._gpu_name} "
                f"(CUDA {self._cuda_version})"
            )
        else:
            self.logger.warning(
                f"No GPU available — all workloads will use CPU or remote API."
            )

        self._detected = True

    @property
    def gpu_available(self) -> bool:
        """True if a CUDA GPU was detected at startup."""
        return self._gpu_available

    @property
    def gpu_name(self) -> str | None:
        """Detected GPU device name, e.g. 'Tesla V100-SXM2-32GB'."""
        return self._gpu_name

    def resolve(
        self,
        capability: DeviceCapability,
        preferred_chain: list[Literal["gpu", "cpu", "remote"]] | None = None,
    ) -> Device:
        """
        Return the best available device for the given capability.

        Uses ``preferred_chain`` if provided, otherwise falls back to the default
        chain for the capability.  Skips GPU if not available; skips CPU for VLM
        (quality unacceptable in volume — spec §6.2).

        Args:
            capability (DeviceCapability): The ML capability being resolved.
            preferred_chain (list | None): Ordered preference list; None → default.

        Returns:
            Device: The first available device in the preference chain.

        Raises:
            RuntimeError: If no device in the chain is available.
        """
        # 1. Build the effective preference chain
        chain: list[Device] = (
            [Device(d) for d in preferred_chain]
            if preferred_chain
            else self._DEFAULT_CHAINS.get(capability, [Device.CPU, Device.REMOTE])
        )

        # 2. Walk the chain and return the first available device
        for device in chain:
            if device == Device.GPU and not self._gpu_available:
                continue  # GPU not available — skip
            return device

        raise RuntimeError(
            f"No available device for capability={capability!r}. "
            f"Chain exhausted: {chain}."
        )

    def snapshot(self) -> DeviceSnapshot:
        """
        Return a read-only gauge of the current resolution state (Brique D monitoring).

        Reports GPU availability plus, for each known capability, the device it would currently
        resolve to using the default chain. Resolution is best-effort: a capability whose chain is
        exhausted is reported as ``"unavailable"`` rather than raising.

        Returns:
            DeviceSnapshot: Immutable view of availability + per-capability device.
        """
        # 1. Resolve each capability against its default chain (never raises here)
        capabilities: dict[str, str] = {}
        for capability in DeviceCapability:
            try:
                capabilities[capability.value] = self.resolve(capability).value
            except RuntimeError:
                capabilities[capability.value] = "unavailable"

        # 2. Pack availability + per-capability mapping into the immutable gauge
        return DeviceSnapshot(
            gpu_available=self._gpu_available,
            gpu_name=self._gpu_name,
            cuda_version=self._cuda_version,
            capabilities=capabilities,
        )
