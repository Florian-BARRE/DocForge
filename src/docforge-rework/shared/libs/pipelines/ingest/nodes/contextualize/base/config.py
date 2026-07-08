# ====== Code Summary ======
# The config base of the contextualizer family. Deliberately empty: contextualize methods are
# STACKABLE links sharing one face — each kind carries only its own knobs, and the shared frame
# needs none. The base exists for family identity (base + register + auto-describe). It also owns
# the default situating instruction shared by the LLM contextualizer and its externalised prep node.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig

# The Anthropic contextual-retrieval instruction: answer with the situating snippet, nothing else.
DEFAULT_SITUATE_PROMPT = (
    "You situate a chunk within its source document to improve search retrieval. "
    "Given the document content and one chunk of it, answer ONLY with 1-2 short sentences "
    "stating what the chunk is about and where it belongs in the document. No preamble."
)


class BaseContextualizerConfig(NodeConfig):
    """Shared contextualizer config (kinds add their own knobs)."""


__all__ = ["BaseContextualizerConfig", "DEFAULT_SITUATE_PROMPT"]
