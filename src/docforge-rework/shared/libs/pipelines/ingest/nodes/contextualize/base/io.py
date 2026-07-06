# ====== Code Summary ======
# The fixed I/O contract shared by EVERY contextualizer: chunks in, the SAME chunks out with
# their ``context`` grown. One face for the whole family — methods STACK in the graph, and the
# wiring order is the order the context pieces accumulate in.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models import Chunk


class ContextualizerConsumes(NodeInput):
    """Input of any contextualizer — the chunks to enrich (raw or already contextualised)."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The chunks to enrich (raw, or already contextualised upstream).",
    )


class ContextualizerProduces(NodeOutput):
    """Output of any contextualizer — the same chunks, ``context`` grown (raw text untouched)."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The SAME chunks, context grown (copies; raw text untouched).",
    )


__all__ = ["ContextualizerConsumes", "ContextualizerProduces"]
