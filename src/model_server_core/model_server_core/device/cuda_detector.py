# ====== Code Summary ======
# CudaDetector: the contract of one "is a CUDA GPU visible?" check, plus NvidiaDriverDetector, the
# torch-free implementation the core ships (the NVIDIA driver's /proc and /dev nodes). A check that
# needs torch or paddle is NOT in the core: the server that owns the heavy dependency implements this
# contract and injects it into the DeviceProbe.

# ====== Standard Library Imports ======
from __future__ import annotations

import pathlib
from abc import ABC, abstractmethod

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class CudaDetector(ABC):
    """Contract: report whether a CUDA GPU is visible to this process."""

    @abstractmethod
    def is_cuda_available(self) -> bool:
        """Whether a CUDA GPU is visible.

        Returns:
            bool: True on a positive GPU signal. An implementation may raise: `DeviceProbe`
                treats any exception as "no GPU".
        """


class NvidiaDriverDetector(CudaDetector, LoggerClass):
    """Detects a GPU from the NVIDIA kernel driver's nodes, without importing any ML library.

    Args:
        proc_version_path (pathlib.Path): File the driver exposes when a GPU and driver are present.
        dev_dir (pathlib.Path): Directory holding `nvidia0`, `nvidia1`... device nodes.
    """

    # Private attributes
    _proc_version_path: pathlib.Path
    _dev_dir: pathlib.Path

    def __init__(
        self,
        *,
        proc_version_path: pathlib.Path = pathlib.Path("/proc/driver/nvidia/version"),
        dev_dir: pathlib.Path = pathlib.Path("/dev"),
    ) -> None:
        LoggerClass.__init__(self)
        self._proc_version_path = proc_version_path
        self._dev_dir = dev_dir

    def is_cuda_available(self) -> bool:
        """Whether the driver's /proc file or a /dev/nvidia* node exists.

        Returns:
            bool: True when either signal is present; False when neither is (or on a read error).
        """
        # 1. Cheapest signal: the driver's version file.
        try:
            if self._proc_version_path.exists():
                return True
        except OSError as exc:
            self.logger.debug(f"{self._proc_version_path} not readable: {exc}")

        # 2. Device nodes granted to the container.
        try:
            return any(node.name.startswith("nvidia") for node in self._dev_dir.iterdir())
        except OSError as exc:
            self.logger.debug(f"{self._dev_dir} not listable: {exc}")
            return False
