# ====== Code Summary ======
# IO contract for the fetch-pdf step: it reads the PDF view key from the parent stage input
# (FromParent, optional — there may be no PDF view) and produces the raw PDF bytes (or None when there
# is no PDF view to fetch). Splitting the download into its own step keeps the parse step purely
# concerned with driving the parser chain.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromParent, NodeInput, NodeOutput


class IngestStageParseStepFetchPdfInput(NodeInput):
    """
    Input of the fetch-pdf step.

    Attributes:
        pdf_key (str | None): Object-store key of the PDF view (from the stage input), or None when
            there is no PDF view (e.g. a plain-text / non-convertible original).
    """

    pdf_key: Annotated[str | None, FromParent(field="pdf_key", required=False)]


class IngestStageParseStepFetchPdfOutput(NodeOutput):
    """
    Output of the fetch-pdf step.

    Attributes:
        pdf_bytes (bytes | None): Raw bytes of the PDF view, or None when there was no PDF to fetch
            (the parse step then produces a degraded empty IR).
    """

    pdf_bytes: bytes | None = None


__all__ = ["IngestStageParseStepFetchPdfInput", "IngestStageParseStepFetchPdfOutput"]
