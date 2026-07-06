# ====== Code Summary ======
# The breadcrumb contextualizer — renders each chunk's heading_path (computed at chunking time)
# as a section trail prefix ("Chapitre 2 > Résultats"). Zero cost, local, and one of the highest
# retrieval gains per token: the section trail disambiguates chunks lexically AND semantically.

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
        default="Section: {path}",
        description="Rendered piece; {path} is the joined heading trail.",
    )
    separator: str = Field(default=" > ", description="Joiner between heading levels.")
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
        "Renders the chunk's heading_path through the template ('Section: A > B'); a chunk "
        "outside any section gets nothing. Zero cost — the trail was computed at chunking time."
    )
    Config = ContextualizerBreadcrumbConfig
    UNIQUE_IN_GRAPH = True

    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """Render the chunk's section trail (None outside any section)."""
        config: ContextualizerBreadcrumbConfig = self.config
        # 1. Keep the deepest max_depth levels (0 = all), then render.
        path = chunks[index].heading_path
        if not path:
            return None
        if config.max_depth > 0:
            path = path[-config.max_depth:]
        return config.template.format(path=config.separator.join(path))


__all__ = ["ContextualizerBreadcrumbNode", "ContextualizerBreadcrumbConfig"]
