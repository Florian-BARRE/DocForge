# ====== Code Summary ======
# The doc_meta contextualizer — anchors every chunk at its DOCUMENT identity. It emits ONE doc
# anchor, identical for every chunk: the declared document title when the caller supplied one,
# otherwise (free, deterministic — never an LLM) the document's FIRST top-level (level-1) heading,
# read off the chunks' heading_path. Zero cost, local; it is the ROOT of the trail the breadcrumb
# then continues, so a flat deck reads "Rapport annuel 2026 › Marge brute" instead of a bare title.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType, Chunk, DocumentIR, SourceDocument

# ====== Local Project Imports ======
from ..base import BaseContextualizerConfig, BaseContextualizerNode, ContextualizerConsumes


class ContextualizerDocMetaConfig(BaseContextualizerConfig):
    """Which declared field anchors the document, and the free fallback when it is absent."""

    title_field: str = Field(
        default="title",
        description="Declared-metadata key holding the document title — the preferred anchor.",
    )
    fallback_to_heading: bool = Field(
        default=True,
        description="When no declared title, anchor on the document's first top-level (level-1) "
        "heading (free, deterministic) instead of emitting nothing.",
    )


class DocMetaConsumes(ContextualizerConsumes):
    """The family face + the source document carrying the declared metadata."""

    source: SourceDocument = Field(
        description="The run's source document (its declared title anchors every chunk)."
    )
    ir: DocumentIR | None = Field(
        default=None,
        description="The document IR — the heading fallback reads its FIRST heading in reading "
        "order (the true title), which a chunk's coalesced heading_path may have lost.",
    )


@NodeRegistry.register("contextualize")
class ContextualizerDocMetaNode(BaseContextualizerNode):
    """Prefix each chunk with the document anchor (declared title, else the first level-1 heading)."""

    KIND = "doc_meta"
    NAME = "Document anchor"
    SUMMARY = "Prefix each chunk with the document anchor (declared title or first heading)."
    HOW_IT_WORKS = (
        "Emits ONE anchor, identical for every chunk: the declared document title when supplied, "
        "else the document's first top-level heading (free, no LLM). It is the root of the trail "
        "the breadcrumb continues. Zero cost."
    )
    Config = ContextualizerDocMetaConfig
    UNIQUE_IN_GRAPH = True
    Consumes = DocMetaConsumes

    async def _contextualize(
        self, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> list[Chunk]:
        """Prefix every chunk with the one document anchor (computed once for the whole document)."""
        anchor = self.__anchor(chunks, data)
        return [self._with_context(chunk, anchor) for chunk in chunks]

    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """Per-chunk hook — the same document anchor for every chunk (None when unavailable)."""
        return self.__anchor(chunks, data)

    def __anchor(self, chunks: list[Chunk], data: DocMetaConsumes) -> str | None:
        """The document anchor: declared title first, then the first heading (title) fallback."""
        config: ContextualizerDocMetaConfig = self.config
        # 1. Prefer the caller-declared title when present and non-empty.
        declared = data.source.declared_meta.get(config.title_field)
        if declared not in (None, ""):
            return str(declared)
        if not config.fallback_to_heading:
            return None
        # 2. The document's TRUE first heading, read off the IR in reading order — the actual title.
        #    A chunk's heading_path is the COMMON section ancestry of its passages, so a first chunk
        #    that coalesced sibling level-1 sections reports []; picking "the first chunk WITH a
        #    heading_path" would then wrongly anchor every chunk on a later section. The IR keeps the
        #    real first heading regardless of how chunks packed.
        if data.ir is not None:
            first_heading = next(
                (
                    block.text.strip()
                    for block in sorted(data.ir.blocks, key=lambda b: b.reading_order)
                    if block.block_type == BlockType.HEADING and block.text and block.text.strip()
                ),
                None,
            )
            if first_heading:
                return first_heading
        # 3. No IR available (e.g. a direct unit construction): the first chunk's own top-level
        #    heading, or nothing — never a later chunk's section, which would misanchor the document.
        return chunks[0].heading_path[0] if chunks and chunks[0].heading_path else None


__all__ = ["ContextualizerDocMetaNode", "ContextualizerDocMetaConfig", "DocMetaConsumes"]
