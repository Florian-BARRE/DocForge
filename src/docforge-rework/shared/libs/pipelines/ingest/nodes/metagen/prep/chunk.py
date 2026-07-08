# ====== Code Summary ======
# The chunk-scope metagen PREP node — resolves the GENERATED/CHUNK targets and emits, per chunk, one
# GenerationRequest per call group carrying the chunk's ENRICHED text (context + raw) and its chunk_id.
# The downstream structgen ForEach turns each request into GeneratedValues; the chunk-apply node merges
# them back. Nothing declared (no chunk-scope target) or no chunks means an empty request list — the
# loop and apply no-op, preserving "nothing declared, nothing spent".

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk, CollectionContract, FieldScope, GenerationRequest

# ====== Local Project Imports ======
from .base import BaseMetagenPrep
from .config import MetagenPrepConfig


class MetagenChunkPrepConfig(MetagenPrepConfig):
    """Chunk-scope prep config (the shared prep knobs are everything it needs)."""


class MetagenChunkPrepConsumes(NodeInput):
    """Input: the chunks to annotate + the contract declaring the fields."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The chunks (each request carries a chunk's enriched text)."
    )
    contract: CollectionContract = Field(
        description="The contract declaring the GENERATED chunk-scope fields to fill."
    )


class MetagenChunkPrepProduces(NodeOutput):
    """Output: one GenerationRequest per (chunk, call group) — the items a structgen ForEach runs."""

    requests: list[GenerationRequest] = Field(
        default_factory=list,
        description="One structured-generation call per (chunk, endpoint group), chunk_id set.",
    )


@NodeRegistry.register("metagen")
class MetagenChunkPrepNode(BaseMetagenPrep):
    """Emit the CHUNK-scope generation requests declared by the contract, chunk by chunk."""

    KIND = "chunk_prep"
    NAME = "Chunk metadata prep"
    SUMMARY = "Emit one structured-generation request per chunk from the contract's chunk-scope fields."
    HOW_IT_WORKS = (
        "Resolves the GENERATED/CHUNK fields (contract declares, targets bind prompt + endpoint per "
        "field) and emits, per chunk, one GenerationRequest per call group over the chunk's ENRICHED "
        "text — no model call here. A bad target fails loudly before any spend."
    )
    Config = MetagenChunkPrepConfig
    Consumes = MetagenChunkPrepConsumes
    Produces = MetagenChunkPrepProduces

    async def run(self, data: MetagenChunkPrepConsumes) -> MetagenChunkPrepProduces:
        """
        Emit the chunk-scope generation requests.

        Args:
            data (MetagenChunkPrepConsumes): The chunks + the contract.

        Returns:
            MetagenChunkPrepProduces: One request per (chunk, call group).
        """
        # 1. What this node must fill — a bad target raises here, before any spend.
        targets = self._resolve_targets(data.contract, FieldScope.CHUNK)
        if not targets or not data.chunks:
            return MetagenChunkPrepProduces(requests=[])

        # 2. One request batch per chunk, on its enriched text, keyed to the chunk.
        requests: list[GenerationRequest] = []
        for chunk in data.chunks:
            requests.extend(
                self._build_requests(chunk.enriched_text, chunk.chunk_id, targets, chunk.chunk_id)
            )
        self.logger.debug(f"Prepared {len(requests)} chunk-scope request(s) over {len(data.chunks)} chunk(s)")
        return MetagenChunkPrepProduces(requests=requests)


__all__ = [
    "MetagenChunkPrepNode",
    "MetagenChunkPrepConfig",
    "MetagenChunkPrepConsumes",
    "MetagenChunkPrepProduces",
]
