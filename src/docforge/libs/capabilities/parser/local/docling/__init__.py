# ---------------------- Provider ---------------------- #
from .core import DoclingBackend

# ---------------------- Config ------------------------ #
# DoclingConfig import triggers @register("parser") — must be imported for auto-registration.
from .config import DoclingConfig

# ------------------- Public API ------------------- #
__all__ = [
    "DoclingBackend",
    "DoclingConfig",
]
