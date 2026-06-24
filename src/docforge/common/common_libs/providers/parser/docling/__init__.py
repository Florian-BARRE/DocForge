# ---------------------- Provider ---------------------- #
# ---------------------- Config ------------------------ #
# DoclingConfig import triggers @register("parser") — must be imported for auto-registration.
from .config import DoclingConfig
from .core import DoclingBackend

# ------------------- Public API ------------------- #
__all__ = [
    "DoclingBackend",
    "DoclingConfig",
]
