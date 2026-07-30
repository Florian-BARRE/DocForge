# ====== Code Summary ======
# The chunk-scope metagen APPLY node — the back half of the externalised chunk metagen. It takes the
# GeneratedValues a structgen ForEach produced (one per chunk, per call group) and merges each into the
# matching chunk's generated_meta, keyed by chunk_id. The merge is ADDITIVE (never a clobber): a
# chunk's pre-existing generated_meta and the values of every group that targeted it accumulate, exactly
# as the old monolithic chunk node merged per-endpoint groups. A chunk with no produced values (a
# skip-terminal's empty result, or simply untargeted) is passed through untouched — the document
# survives one failed request.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk, GeneratedValues


class MetagenChunkApplyConfig(NodeConfig):
    """No knobs — merging generated values into chunks is a pure structural join."""


class MetagenChunkApplyConsumes(NodeInput):
    """Input: the chunks to annotate + the generated values the chain produced."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The chunks to merge generated metadata into."
    )
    values: list[GeneratedValues] = Field(
        default_factory=list,
        description="The generated values (each keyed to its chunk_id) the structgen loop produced.",
    )


class MetagenChunkApplyProduces(NodeOutput):
    """Output: the same chunks, generated_meta merged (copies, raw text untouched)."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The SAME chunks, generated_meta merged (copies)."
    )


@NodeRegistry.register("metagen")
class MetagenChunkApplyNode(ActionNode):
    """Merge the structgen loop's chunk-scope values back onto their chunks."""

    KIND = "chunk_apply"
    SELECTABLE = False  # internal wiring — the stage builder emits it, not a user-picked method
    NAME = "Chunk metadata apply"
    SUMMARY = "Merge the generated chunk-scope values back onto their chunks (by chunk_id)."
    HOW_IT_WORKS = (
        "Indexes the produced GeneratedValues by chunk_id and merges each into the matching chunk's "
        "generated_meta (additively, never clobbering pre-existing keys). A chunk with no usable "
        "values is passed through untouched — one failed request never fails the document."
    )
    Config = MetagenChunkApplyConfig
    Consumes = MetagenChunkApplyConsumes
    Produces = MetagenChunkApplyProduces

    async def run(self, data: MetagenChunkApplyConsumes) -> MetagenChunkApplyProduces:
        """
        Merge the generated values into their chunks.

        Args:
            data (MetagenChunkApplyConsumes): The chunks + the generated values.

        Returns:
            MetagenChunkApplyProduces: The chunks with generated_meta merged (copies).
        """
        # 1. Index the produced values by chunk; a chunk's groups accumulate (per_field / multi-node).
        by_chunk: dict[str, dict[str, Any]] = {}
        for produced in data.values:
            if produced.chunk_id is None or not produced.values:
                continue
            by_chunk.setdefault(produced.chunk_id, {}).update(produced.values)

        # 2. Merge onto each chunk — additive, never clobbering the accumulated dict.
        chunks: list[Chunk] = []
        for chunk in data.chunks:
            merged = by_chunk.get(chunk.chunk_id)
            if not merged:
                chunks.append(chunk)
                continue
            chunks.append(
                chunk.model_copy(update={"generated_meta": {**chunk.generated_meta, **merged}})
            )
        annotated = sum(1 for chunk in chunks if chunk.generated_meta)
        self.logger.debug(f"Merged generated metadata onto {annotated}/{len(chunks)} chunk(s)")
        return MetagenChunkApplyProduces(chunks=chunks)


__all__ = [
    "MetagenChunkApplyNode",
    "MetagenChunkApplyConfig",
    "MetagenChunkApplyConsumes",
    "MetagenChunkApplyProduces",
]
