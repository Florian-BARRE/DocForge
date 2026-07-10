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
from shared_libs.public_models import Chunk, SourceDocument

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

    def __anchor(self, chunks: list[Chunk], data: ContextualizerConsumes) -> str | None:
        """The document anchor: declared title first, then the first level-1 heading fallback."""
        config: ContextualizerDocMetaConfig = self.config
        # 1. Prefer the caller-declared title when present and non-empty.
        declared = data.source.declared_meta.get(config.title_field)
        if declared not in (None, ""):
            return str(declared)
        # 2. Fall back (free, deterministic) to the document's first top-level heading.
        if config.fallback_to_heading:
            return next((chunk.heading_path[0] for chunk in chunks if chunk.heading_path), None)
        return None


__all__ = ["ContextualizerDocMetaNode", "ContextualizerDocMetaConfig", "DocMetaConsumes"]
