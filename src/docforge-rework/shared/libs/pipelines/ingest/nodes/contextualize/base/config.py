# ====== Code Summary ======
# The config base of the contextualizer family. Deliberately empty: contextualize methods are
# STACKABLE links sharing one face — each kind carries only its own knobs, and the shared frame
# needs none. The base exists for family identity (base + register + auto-describe).

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseContextualizerConfig(NodeConfig):
    """Shared contextualizer config (kinds add their own knobs)."""


__all__ = ["BaseContextualizerConfig"]
