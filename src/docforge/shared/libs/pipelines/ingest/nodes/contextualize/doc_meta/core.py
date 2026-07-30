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

# Table-of-contents heading titles (normalized, lowercased) — mirrors the chunker's own ToC
# allow-list (PassageProjector._TOC_TITLES): a ToC heading is furniture, never a document title, so
# the IR-fallback anchor must skip it. Kept small and multilingual; extend both lists together.
_TOC_TITLES = frozenset(
    {"contents", "table of contents", "toc", "sommaire", "table des matières", "índice"}
)


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
        """Prefix every chunk with the one document anchor (computed once for the whole document).

        A chunk that already OPENS with the anchor text (the coalesced first chunk, whose title
        section the chunker inlined) is left alone — prefixing it would duplicate the title.
        """
        anchor = self.__anchor(chunks, data)
        return [self._with_context(chunk, self.__anchor_for(chunk, anchor)) for chunk in chunks]

    @staticmethod
    def __anchor_for(chunk: Chunk, anchor: str | None) -> str | None:
        """The anchor to prefix onto this chunk — None when the chunker already inlined it.

        The chunker inlines a coalesced section heading as its OWN line (``"Title\\n\\n<body>"``),
        so the title duplicates the anchor only when the chunk's FIRST LINE is exactly the anchor.
        Matching a bare ``startswith`` instead would wrongly suppress the anchor on any chunk whose
        prose merely opens with the title word (title "Overview", body "Overview of the topology…"),
        dropping the anchor that every sibling carries — so compare the first line, not a prefix.
        """
        if anchor and chunk.text.lstrip().split("\n", 1)[0].strip() == anchor:
            return None
        return anchor

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
        # 2. The BODY chunks are already role-filtered (furniture/ToC excluded), so the first body
        #    chunk's own top-level heading is the title AND cannot be a table-of-contents heading —
        #    this is the safe, common path.
        if chunks and chunks[0].heading_path:
            return chunks[0].heading_path[0]
        # 3. That path yields nothing only when the first chunk COALESCED sibling level-1 sections
        #    (its common heading_path is []) — the flat HTML->PDF case. Recover the real title from
        #    the IR's first TOP-LEVEL (level-1) heading in reading order, skipping a table-of-contents
        #    heading (which is furniture, never the title).
        if data.ir is not None:
            headings = [
                block
                for block in sorted(data.ir.blocks, key=lambda b: b.reading_order)
                if block.block_type == BlockType.HEADING
                and block.text
                and block.text.strip()
                and block.text.strip().lower() not in _TOC_TITLES
            ]
            top = next((block for block in headings if block.level == 1), None) or (
                headings[0] if headings else None
            )
            if top:
                return top.text.strip()
        return None


__all__ = ["ContextualizerDocMetaNode", "ContextualizerDocMetaConfig", "DocMetaConsumes"]
