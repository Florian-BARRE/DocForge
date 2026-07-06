# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import AdmissionConfig, AdmissionNode

# ------------------- Public API ------------------- #
__all__ = ["AdmissionNode", "AdmissionConfig"]
