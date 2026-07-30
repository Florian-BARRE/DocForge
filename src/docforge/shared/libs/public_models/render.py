# ====== Code Summary ======
# The page renders the parse stage produces alongside the completed IR: one rasterized image per
# page. They serve the highlight-on-page UI; the worker stores them as blobs at persist time
# (page.render_blob_hash). Figure crops do NOT live here — they are embedded in the IR itself
# (Block.figure.crop), which leaves parse "ultra complet".

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .base import Artifact


class PageRender(BaseModel):
    """One rasterized page."""

    page_number: int = Field(description="0-indexed page number.")
    image: bytes = Field(description="PNG bytes of the rendered page.")
    width: int
    height: int


class PageRenders(Artifact):
    """Every page render of the document."""

    pages: list[PageRender] = Field(default_factory=list)


__all__ = ["PageRender", "PageRenders"]
