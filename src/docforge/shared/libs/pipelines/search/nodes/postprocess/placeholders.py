# ====== Code Summary ======
# Future post-process methods (SELECTABLE=False): dedup-by-document, MMR diversity, parent-expand
# (small-to-big) and context-assemble. Each consumes and produces RankedHits (they refine the hit
# set in place), registered with typed described faces for discoverability; bodies raise until the
# post-process phase (research P5).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import EncodedQuery, RankedHits

# ====== Local Project Imports ======
from ..placeholder import PlaceholderNode


class _PostprocessPlaceholderConfig(NodeConfig):
    """Knob-less config shared by the post-process placeholders."""


class _RefineHits(NodeInput):
    """Consumes the ranked hits to refine."""

    ranked: RankedHits = Field(description="The ranked hits to refine.")


class _RefineHitsWithQuery(NodeInput):
    """Consumes the ranked hits + the query vectors (for a similarity-aware refinement)."""

    ranked: RankedHits = Field(description="The ranked hits to refine.")
    encoded: EncodedQuery = Field(description="The query vectors, for similarity-aware diversity.")


class _RefinedHits(NodeOutput):
    """Produces the refined ranked hits."""

    ranked: RankedHits = Field(description="The refined ranked hits.")


@NodeRegistry.register("postprocess")
class PostprocessDedupDocumentNode(PlaceholderNode):
    """Keep at most one hit per document (future)."""

    KIND = "dedup_document"
    NAME = "Dedup by document"
    SUMMARY = "Collapse the hits to at most one per source document."
    Config = _PostprocessPlaceholderConfig
    Consumes = _RefineHits
    Produces = _RefinedHits


@NodeRegistry.register("postprocess")
class PostprocessMmrNode(PlaceholderNode):
    """Maximal-marginal-relevance re-ranking for diversity (future)."""

    KIND = "mmr"
    NAME = "MMR diversity"
    SUMMARY = "Re-order hits for λ-weighted diversity vs relevance (MMR)."
    Config = _PostprocessPlaceholderConfig
    Consumes = _RefineHitsWithQuery
    Produces = _RefinedHits


@NodeRegistry.register("postprocess")
class PostprocessParentExpandNode(PlaceholderNode):
    """Expand each hit to its parent chunk — small-to-big (future)."""

    KIND = "parent_expand"
    NAME = "Parent expand"
    SUMMARY = "Replace each hit with its larger parent chunk (small-to-big retrieval)."
    Config = _PostprocessPlaceholderConfig
    Consumes = _RefineHits
    Produces = _RefinedHits


@NodeRegistry.register("postprocess")
class PostprocessAssembleNode(PlaceholderNode):
    """Assemble the hits into a single context passage (future)."""

    KIND = "assemble"
    NAME = "Assemble context"
    SUMMARY = "Concatenate/de-overlap the hits into one context passage for a reader."
    Config = _PostprocessPlaceholderConfig
    Consumes = _RefineHits
    Produces = _RefinedHits


__all__ = [
    "PostprocessDedupDocumentNode",
    "PostprocessMmrNode",
    "PostprocessParentExpandNode",
    "PostprocessAssembleNode",
]
