# ====== Code Summary ======
# The chunk-scope metagen node — fills every GENERATED/CHUNK field of the contract, one
# structured generation per chunk (bounded concurrency). The chunk's ENRICHED text (context +
# raw) feeds the model — the breadcrumb/LLM context helps extraction. Values land on
# Chunk.generated_meta as copies; a failing chunk keeps an empty dict (skip_fields), the
# document never fails for one 503.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk, CollectionContract, FieldScope

# ====== Local Project Imports ======
from ..base import BaseMetagenConfig, BaseMetagenNode


class MetagenChunkConfig(BaseMetagenConfig):
    """Chunk-scope metagen config (the shared knobs are everything it needs)."""


class MetagenChunkConsumes(NodeInput):
    """Input: the chunks to annotate + the contract."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The chunks (the generation text source).",
    )
    contract: CollectionContract = Field(
        description="The contract declaring the GENERATED fields to fill."
    )


class MetagenChunkProduces(NodeOutput):
    """Output: the same chunks, ``generated_meta`` filled (copies, raw text untouched)."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The SAME chunks, generated_meta filled (copies).",
    )


@NodeRegistry.register("metagen")
class MetagenChunkNode(BaseMetagenNode):
    """Generate the CHUNK-scope metadata declared by the contract, chunk by chunk."""

    KIND = "chunk"
    NAME = "Chunk metadata generation"
    SUMMARY = "Fill the contract's GENERATED chunk-scope fields for every chunk."
    HOW_IT_WORKS = (
        "Resolves the GENERATED/CHUNK fields (contract declares, targets bind prompt + LLM per "
        "field) and runs one structured generation per chunk on its ENRICHED text, under a "
        "concurrency bound. Values are coerced to their contract type and land on the chunk's "
        "generated_meta; a failing chunk keeps an empty dict — the document survives."
    )
    Config = MetagenChunkConfig
    Consumes = MetagenChunkConsumes
    Produces = MetagenChunkProduces

    async def run(self, data: MetagenChunkConsumes) -> MetagenChunkProduces:
        """
        Generate the chunk-scope values for every chunk.

        Args:
            data (MetagenChunkConsumes): The chunks + the contract.

        Returns:
            MetagenChunkProduces: The chunks with generated_meta filled (copies).
        """
        config: MetagenChunkConfig = self.config
        # 1. What this node must fill — nothing declared means nothing spent.
        targets = self._resolve_targets(data.contract, FieldScope.CHUNK)
        if not targets or not data.chunks:
            return MetagenChunkProduces(chunks=list(data.chunks))

        # 2. One generation per chunk, bounded; the ENRICHED text feeds the model.
        semaphore = asyncio.Semaphore(config.max_concurrency)

        async def annotate(chunk: Chunk) -> Chunk:
            async with semaphore:
                values = await self._generate_values(chunk.enriched_text, targets)
            # MERGE with what a previous metagen node already generated (field subsets may
            # be split across nodes) — never clobber the accumulated dict.
            if not values:
                return chunk
            return chunk.model_copy(
                update={"generated_meta": {**chunk.generated_meta, **values}}
            )

        chunks = list(await asyncio.gather(*(annotate(chunk) for chunk in data.chunks)))
        annotated = sum(1 for chunk in chunks if chunk.generated_meta)
        self.logger.info(f"Annotated {annotated}/{len(chunks)} chunk(s) with generated metadata")
        return MetagenChunkProduces(chunks=chunks)


__all__ = ["MetagenChunkNode", "MetagenChunkConfig", "MetagenChunkConsumes", "MetagenChunkProduces"]
