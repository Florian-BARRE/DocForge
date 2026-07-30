# ====== Code Summary ======
# The search RUN-INPUT artefacts — the typed entry contract a FromRunInput binding targets, the
# search analog of ingestion's SourceDocument. RawQuery carries the caller's raw ask (text, depth,
# flags); QueryFilters carries the caller's raw filter map. The query-intake node consumes both and
# normalises them into a QuerySpec. They are Artifacts because a node's typed slots may only bind
# to Artifact-typed run inputs.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from ..base import Artifact

# ====== Local Project Imports ======
from .target import SearchTarget, default_content_targets


class RawQuery(Artifact):
    """
    The caller's raw query — the run-input the query-intake node normalises.

    Attributes:
        text (str): The raw query text as typed by the caller (un-normalised).
        top_k (int): How many hits the caller wants back (the delivered result-set size).
        search_targets (list[SearchTarget]): The caller's field × modality selection carried into
            the QuerySpec. Defaults to content on both axes; an empty list is normalised back to
            that default (a spec never has zero targets).
        flags (dict): Free-form retrieval switches (e.g. ``use_late_interaction``) carried into
            the QuerySpec and read by the encode/retrieve/rerank stages.
    """

    text: str = Field(description="The raw query text as typed by the caller (un-normalised).")
    top_k: int = Field(
        default=10, gt=0, description="How many hits to return (delivered set size)."
    )
    search_targets: list[SearchTarget] = Field(
        default_factory=default_content_targets,
        description="Field × modality selection (content and/or metadata); default is content on "
        "both semantic and lexical.",
    )
    flags: dict = Field(
        default_factory=dict,
        description="Free-form retrieval switches (e.g. use_late_interaction) carried downstream.",
    )


class QueryFilters(Artifact):
    """
    The caller's raw filter map — the run-input the query-intake node validates and structures.

    Attributes:
        filters (dict): The raw ``field → value`` filter map to apply to the retrieval; empty
            when the caller filters on nothing.
    """

    filters: dict = Field(
        default_factory=dict, description="Raw field → value filter map to apply to retrieval."
    )


__all__ = ["RawQuery", "QueryFilters"]
