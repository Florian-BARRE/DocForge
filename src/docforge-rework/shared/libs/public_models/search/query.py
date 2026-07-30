# ====== Code Summary ======
# The query-side flow artefacts: QuerySpec (the normalised, retrieval-ready query — text, filters,
# depth knobs and flags) and EncodedQuery (the query's vectors, the exact mirror of a chunk's
# ChunkVectors so the retriever compares like with like). Both subclass Artifact: they are bound to
# node slots and compared by the graph validator through a plain subclass check.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from ..base import Artifact
from ..embed import SparseVector

# ====== Local Project Imports ======
from .target import SearchTarget, default_content_targets


class QuerySpec(Artifact):
    """
    The normalised, retrieval-ready query — the output of the query-intake stage.

    Attributes:
        text (str): The cleaned query text (trimmed, case-folded, inline filters stripped).
        filters (dict): The structured filter map applied to the retrieval (field → value).
        language (str | None): The detected query language (ISO code) or None when not detected.
        top_k (int): How many hits the caller asked for — the size of the delivered result set.
        candidate_k (int): The over-sampled retrieval depth (candidate pool before rerank/cut).
        search_targets (list[SearchTarget]): What to search — which fields (content and/or metadata)
            on which modalities (semantic/lexical). Defaults to content on both axes (today's plain
            query), so an untouched spec behaves exactly as before targets existed.
        flags (dict): Free-form retrieval switches carried downstream (e.g.
            ``use_late_interaction``), read by the encode/retrieve/rerank stages.
    """

    text: str = Field(
        description="The cleaned query text (trimmed, case-folded, filters stripped)."
    )
    filters: dict = Field(
        default_factory=dict,
        description="Structured filter map applied to retrieval (field → value).",
    )
    language: str | None = Field(
        default=None, description="Detected query language (ISO code) or None."
    )
    top_k: int = Field(
        description="How many hits the caller asked for (delivered result-set size)."
    )
    candidate_k: int = Field(
        description="Over-sampled retrieval depth (candidate pool before cut)."
    )
    search_targets: list[SearchTarget] = Field(
        default_factory=default_content_targets,
        description="Fields × modalities to search (content and/or metadata); default is content "
        "on both semantic and lexical.",
    )
    flags: dict = Field(
        default_factory=dict,
        description="Free-form retrieval switches carried downstream (e.g. use_late_interaction).",
    )


class EncodedQuery(Artifact):
    """
    The query's vectors — the query-side mirror of a chunk's ChunkVectors.

    Attributes:
        dense (list[float]): The dense query vector (always present — a query must be searchable).
        sparse (SparseVector | None): The lexical query vector; None when the collection's
            embedder has no sparse axis.
        colbert (list[list[float]] | None): The ColBERT multi-vector (one vector per query token);
            None unless late interaction is on AND the collection indexed ColBERT.
        model (str): The embedding model that produced the vectors (provenance; must match the
            model the chunks were indexed with).
    """

    dense: list[float] = Field(
        default_factory=list, description="The dense query vector (always present)."
    )
    sparse: SparseVector | None = Field(
        default=None,
        description="The lexical query vector; None when the embedder has no sparse axis.",
    )
    colbert: list[list[float]] | None = Field(
        default=None,
        description="The ColBERT multi-vector (one vector per query token); None unless late "
        "interaction is on and the collection indexed ColBERT.",
    )
    model: str = Field(
        default="", description="The embedding model that produced the vectors (provenance)."
    )


__all__ = ["QuerySpec", "EncodedQuery"]
