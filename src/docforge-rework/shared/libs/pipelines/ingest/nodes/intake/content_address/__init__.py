# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import ContentAddressConfig, ContentAddressNode

# ------------------- Public API ------------------- #
__all__ = ["ContentAddressNode", "ContentAddressConfig"]
