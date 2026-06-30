# ====== Code Summary ======
# ContextualizeConfig — the per-collection knobs of the contextualize stage, declared as the node's
# ``Config``. It controls how each chunk's ``embed_text`` header is assembled before the embedder sees
# it (the context that lifts retrieval quality). Every field carries a ``description`` so the discovery
# API can render a labelled form with zero hardcoded text. Ported from the v1 contextualize config.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class ContextualizeConfig(BaseModel):
    """
    Contextualize stage configuration — the chunk ``embed_text`` header template.

    Default template (both toggles on)::

        <doc_title> > <H1> > <H2> > <H3>

        <chunk body>

    Attributes:
        include_doc_title (bool): Prepend the document title to the header.
        include_breadcrumb (bool): Include the heading breadcrumb (``H1 > H2 > H3``).
        breadcrumb_separator (str): Separator joining title + breadcrumb segments.
        header_body_separator (str): Separator joining the header line to the chunk body.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    include_doc_title: bool = Field(
        default=True,
        description=(
            "Prepend the document title to the chunk header (skipped when it already equals the "
            "first breadcrumb segment, to avoid duplication)."
        ),
    )
    include_breadcrumb: bool = Field(
        default=True,
        description=(
            "Include the heading breadcrumb (e.g. 'Part 1 > Chapter 2'). When off, only the title "
            "is prepended and the chunk body stays uncontextualised (useful for benchmarks)."
        ),
    )
    breadcrumb_separator: str = Field(
        default=" > ",
        min_length=1,
        max_length=8,
        description="Separator joining the document title and the breadcrumb segments.",
    )
    header_body_separator: str = Field(
        default="\n\n",
        min_length=1,
        max_length=8,
        description="Separator joining the assembled header line to the chunk body.",
    )


__all__ = ["ContextualizeConfig"]
