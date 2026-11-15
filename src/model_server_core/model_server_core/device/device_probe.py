# ====== Code Summary ======
# DeviceProbe: cheap, memoized probe reporting the compute device this container runs on ("cuda" or
# "cpu"). It feeds the GET /health `device` field. The probe is a chain of injected CudaDetectors, so
# the core stays torch-free: a server that decides on torch (bge) or paddle injects its own detector.
# A health probe must never raise: a failing detector degrades to "no GPU from this detector".

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .cuda_detector import CudaDetector, NvidiaDriverDetector
from .device import Device


class DeviceProbe(LoggerClass):
    """Resolves the runtime device from an ordered chain of detectors, once.

    Args:
        detectors (Sequence[CudaDetector] | None): Checked in order; the first positive one wins.
            Defaults to the torch-free `NvidiaDriverDetector`.
    """

    # Private attributes
    _detectors: tuple[CudaDetector, ...]
    _cuda_available: bool | None

    def __init__(self, detectors: Sequence[CudaDetector] | None = None) -> None:
        LoggerClass.__init__(self)
        self._detectors = tuple(detectors) if detectors is not None else (NvidiaDriverDetector(),)
        self._cuda_available = None

    # =======================
    #   Private Methods
    # =======================
    def _probe(self) -> bool:
        """Ask each detector in order, isolating the failure of each."""
        for detector in self._detectors:
            try:
                if detector.is_cuda_available():
                    return True
            except Exception as exc:  # noqa: BLE001 - a health probe must never raise
                self.logger.warning(
                    f"{type(detector).__name__} failed ({exc}); treating it as 'no GPU'."
                )
        return False

    # =======================
    #   Public Methods
    # =======================
    def cuda_available(self) -> bool:
        """Whether a CUDA GPU is visible, memoized (the device set is fixed for the process).

        Returns:
            bool: True when any detector reports a GPU.
        """
        if self._cuda_available is None:
            self._cuda_available = self._probe()
        return self._cuda_available

    def device(self) -> Device:
        """The runtime compute device.

        Returns:
            Device: `Device.CUDA` when a GPU is visible, else `Device.CPU`.
        """
        return Device.CUDA if self.cuda_available() else Device.CPU
