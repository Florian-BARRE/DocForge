# ---------------------- Base ---------------------- #
# An abstract mid-layer: it registers NOTHING (no @NodeRegistry.register), so importing it during the
# family auto-discovery is a no-op beyond defining the shared scaffold of the four sidecar parsers.
from .config import SidecarParserConfig
from .geometry import SidecarGeometry
from .mapper import SidecarIRMapper
from .node import SidecarParserNode
from .table import SidecarTableFlattener

# ------------------- Public API ------------------- #
__all__ = [
    "SidecarParserConfig",
    "SidecarGeometry",
    "SidecarIRMapper",
    "SidecarParserNode",
    "SidecarTableFlattener",
]
