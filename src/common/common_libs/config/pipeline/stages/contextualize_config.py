# ====== Code Summary ======
# S5 ContextualizeConfig: controls how each chunk's embed_text header is assembled
# before the embedder sees it. Part of the S5 contextualization stage configuration.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ContextualizeConfig(BaseModel):
    """
    S5 contextualization configuration — controls how each chunk's ``embed_text`` header
    is assembled before the embedder sees it.

    The default template is::

        <doc_title> > <H1> > <H2> > <H3>

        <chunk body>

    Toggle ``include_doc_title`` or ``include_breadcrumb`` to flatten the header; adjust
    ``breadcrumb_separator`` / ``header_body_separator`` to match the embedder's preferred
    style (e.g. some BGE-M3 prompts perform better with newlines instead of " > ").

    Attributes:
        include_doc_title (bool): Prepend ``DocumentIR.title`` to the header when the
            title is not already the first breadcrumb segment.
        include_breadcrumb (bool): Include the heading breadcrumb (``H1 > H2 > H3``).
            When False, only the doc title (if enabled) is prepended — the chunk body
            stays uncontextualised, which is sometimes useful for benchmarks.
        breadcrumb_separator (str): Joins title + breadcrumb segments (default ``" > "``).
        header_body_separator (str): Joins the header line to the chunk body
            (default ``"\\n\\n"``).
    """

    include_doc_title: bool = True
    include_breadcrumb: bool = True
    breadcrumb_separator: str = Field(default=" > ", min_length=1, max_length=8)
    header_body_separator: str = Field(default="\n\n", min_length=1, max_length=8)
