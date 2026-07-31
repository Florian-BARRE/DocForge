# ====== Code Summary ======
# The breadcrumb contextualizer — renders each chunk's heading_path (computed at chunking time)
# as a section trail ("Analyse financière › Marge brute"). Zero cost, local, and one of the highest
# retrieval gains per token: the section trail disambiguates chunks lexically AND semantically. It
# CONTINUES the doc anchor already in context (from doc_meta) as ONE trail line — it joins with its
# own separator and drops a leading level that merely repeats the anchor (the anchored section).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk

# ====== Local Project Imports ======
from ..base import BaseContextualizerConfig, BaseContextualizerNode, ContextualizerConsumes


class ContextualizerBreadcrumbConfig(BaseContextualizerConfig):
    """Breadcrumb rendering knobs."""

    template: str = Field(
        default="{path}",
        description="Rendered piece; {path} is the joined heading trail (no fixed prefix — the "
        "trail reads as the continuation of the doc anchor).",
    )
    separator: str = Field(
        default=" › ",
        description="Joiner between heading levels AND onto the doc anchor already in context.",
    )
    max_depth: int = Field(
        default=0, ge=0, description="Deepest levels kept (0 = the whole trail)."
    )


@NodeRegistry.register("contextualize")
class ContextualizerBreadcrumbNode(BaseContextualizerNode):
    """Prefix each chunk with its rendered section trail."""

    KIND = "breadcrumb"
    NAME = "Breadcrumb"
    SUMMARY = "Prefix each chunk with its section trail (heading path)."
    HOW_IT_WORKS = (
        "Renders the chunk's heading_path through the template ('A › B') as ONE trail continuing "
        "the doc anchor already in context; a chunk outside any section gets nothing, and a level "
        "that merely repeats the anchor is dropped. Zero cost — the trail was computed at chunking."
    )
    Config = ContextualizerBreadcrumbConfig
    UNIQUE_IN_GRAPH = True

    def _context_joiner(self) -> str:
        """Attach the section trail onto the doc anchor with the trail separator (ONE prefix line)."""
        return self.config.separator

    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """Render the chunk's section trail (None outside any section)."""
        config: ContextualizerBreadcrumbConfig = self.config
        # 1. Keep the deepest max_depth levels (0 = all).
        path = chunks[index].heading_path
        if not path:
            return None
        if config.max_depth > 0:
            path = path[-config.max_depth :]
        # 2. Drop a leading level that repeats the doc anchor already ending the accumulated trail
        #    (this chunk lives in the anchored section) — the prefix must name it only once.
        existing = chunks[index].context
        if path and existing and existing.split(config.separator)[-1].strip() == path[0].strip():
            path = path[1:]
        # 2b. Drop a leading level the chunk's BODY already opens with. The chunker inlines a
        #     coalesced/single section heading as the body's first line ("Title\n\n<body>"); when
        #     that heading is also the trail's top level, the title would show once here and again
        #     in the body. doc_meta suppresses its OWN anchor for exactly this reason (its body-first-
        #     line check), so the trail must not re-introduce the title it dropped.
        if path:
            body_first_line = chunks[index].text.lstrip().split("\n", 1)[0].strip()
            if path[0].strip() == body_first_line:
                path = path[1:]
        if not path:
            return None
        # 3. Render the (deduped) trail; the joiner attaches it onto the anchor as one line.
        return config.template.format(path=config.separator.join(path))


__all__ = ["ContextualizerBreadcrumbNode", "ContextualizerBreadcrumbConfig"]
