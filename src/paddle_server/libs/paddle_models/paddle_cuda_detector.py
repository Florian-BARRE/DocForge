# ====== Code Summary ======
# PaddleCudaDetector: the PaddlePaddle fallback of the Paddle host's "is a CUDA GPU visible?" check.
# The core DeviceProbe asks the torch-free NvidiaDriverDetector first (the NVIDIA driver's /proc and
# /dev nodes), then this detector, which asks Paddle's own runtime (the library the pipelines run on,
# NOT torch): a CUDA-compiled wheel WITH at least one visible device. It implements the
# model_server_core CudaDetector contract. A paddle that cannot be imported raises: the probe treats
# any exception as "no GPU" and reports "cpu", the safe and honest answer.

# ====== Third-Party Library Imports ======
from model_server_core import CudaDetector


class PaddleCudaDetector(CudaDetector):
    """Detects a CUDA GPU through PaddlePaddle's runtime check (imported lazily)."""

    def is_cuda_available(self) -> bool:
        """Whether PaddlePaddle is CUDA-compiled and sees at least one GPU.

        Returns:
            bool: True when paddle is compiled with CUDA and a device is visible.

        Raises:
            ImportError: When paddle is not importable (the DeviceProbe degrades it to "no GPU").
        """
        import paddle  # noqa: PLC0415 (lazy: keep the ML stack out of the module top-level)

        return bool(paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0)
