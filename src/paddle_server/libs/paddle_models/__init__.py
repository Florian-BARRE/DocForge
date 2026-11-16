# ------------------- Service ------------------- #
# ------------------- Device ------------------- #
from .paddle_cuda_detector import PaddleCudaDetector
from .paddle_models_service import PaddleModelsService

# ------------------- Public API ------------------- #
__all__ = [
    "PaddleCudaDetector",
    "PaddleModelsService",
]
