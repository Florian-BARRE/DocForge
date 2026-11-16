# ====== Code Summary ======
# TorchCudaDetector: the torch fallback of the MinerU host's "is a CUDA GPU visible?" check. The core
# DeviceProbe asks the torch-free NvidiaDriverDetector first (the NVIDIA driver's /proc and /dev nodes,
# so the common GPU case never imports torch), then this detector, which asks torch (the library the
# MinerU VLM loads through). It implements the model_server_core CudaDetector contract. A torch that
# cannot be imported (the -cpu wiring image) raises: the probe treats any exception as "no GPU".

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
