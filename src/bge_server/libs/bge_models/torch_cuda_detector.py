# ====== Code Summary ======
# TorchCudaDetector: the "is a CUDA GPU visible?" check of the BGE host, answered by torch (the
# library the BGE models load through, so the source of truth). It implements the model_server_core
# CudaDetector contract and is injected into the core DeviceProbe, which feeds the GET /health
# `device` field. A torch that cannot be imported (the -cpu wiring image) raises: the probe treats
# any exception as "no GPU" and reports "cpu", the safe and honest answer.

# ====== Third-Party Library Imports ======
from model_server_core import CudaDetector


class TorchCudaDetector(CudaDetector):
    """Detects a CUDA GPU through `torch.cuda.is_available()` (imported lazily)."""

    def is_cuda_available(self) -> bool:
        """Whether torch reports a CUDA GPU.

        Returns:
            bool: True when torch sees a CUDA device.

        Raises:
            ImportError: When torch is not importable (the DeviceProbe degrades it to "no GPU").
        """
        import torch  # noqa: PLC0415 (lazy: keep the ML stack out of the module top-level)

        return bool(torch.cuda.is_available())
