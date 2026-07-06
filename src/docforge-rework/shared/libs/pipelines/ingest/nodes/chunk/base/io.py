# ====== Code Summary ======
# The fixed I/O contract shared by EVERY chunking method: the ENRICHED IR in, the ordered raw
# chunks out. Interchangeability is the point — the UI picks the method, the faces never change.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models import Chunk, DocumentIR


class ChunkerConsumes(NodeInput):
    """Input of any chunker — the ENRICHED IR (figure descriptions aboard)."""

    ir: DocumentIR = Field(description="The ENRICHED IR (figure descriptions aboard).")


class ChunkerProduces(NodeOutput):
    """Output of any chunker — the raw retrieval units, in reading order."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The raw retrieval units, in reading order.",
    )


__all__ = ["ChunkerConsumes", "ChunkerProduces"]
