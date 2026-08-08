# ---------------------- Base ---------------------- #
# An abstract mid-layer: it registers NOTHING (no @NodeRegistry.register), so importing it during the
# family auto-discovery is a no-op beyond defining the shared scaffold.
from .node import BaseDoclingParserNode

# ------------------- Public API ------------------- #
__all__ = ["BaseDoclingParserNode"]
