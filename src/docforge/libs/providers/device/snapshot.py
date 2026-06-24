# ====== Code Summary ======
# DeviceSnapshot — an immutable, read-only gauge of the device manager's current resolution state
# (Brique D). It feeds the monitoring "resources" panel without exposing any allocation logic:
# GPU availability + the device each capability would currently resolve to.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """
    Read-only view of the device manager's resolution state at a point in time.

    Attributes:
        gpu_available (bool): Whether a CUDA GPU was detected at startup.
        gpu_name (str | None): Detected GPU device name (None on CPU-only hosts).
        cuda_version (str | None): Detected CUDA toolkit version (None on CPU-only hosts).
        capabilities (dict[str, str]): capability name → device it currently resolves to
            (e.g. {"vlm": "remote", "embed": "cpu"}).
    """

    gpu_available: bool
    gpu_name: str | None = None
    cuda_version: str | None = None
    capabilities: dict[str, str] = field(default_factory=dict)


# ------------------- Public API ------------------- #
__all__ = ["DeviceSnapshot"]
