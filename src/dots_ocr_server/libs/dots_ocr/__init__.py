# ------------------- Service ------------------- #
from .service import DotsOcrService

# ------------------- Device ------------------- #
from .torch_cuda_detector import TorchCudaDetector

# ------------------- Public API ------------------- #
__all__ = [
    "DotsOcrService",
    "TorchCudaDetector",
]
