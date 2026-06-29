# ====== Code Summary ======
# IO contract for the parse step: it consumes the PDF bytes from the fetch-pdf sibling (optional —
# None means no PDF view) and the identity fields (doc id, source hash, page count) from the parent
# stage input, and produces the canonical IR plus the degraded flag (True when no parse was produced)
# that the figure-render and markdown steps branch on.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput


class IngestStageParseStepParseInput(NodeInput):
    """
    Input of the parse step.

    Attributes:
        pdf_bytes (bytes | None): The PDF view bytes (from the fetch-pdf step), or None when there is
            no PDF view to parse.
        doc_id (str): The effective document id (from the stage input).
        source_hash (str): The original content address (from the stage input).
        page_count (int | None): Page count of the PDF view (from the stage input), or None.
    """

    pdf_bytes: Annotated[
        bytes | None, FromSibling(producer="fetch_pdf", field="pdf_bytes", required=False)
    ]
    doc_id: Annotated[str, FromParent(field="doc_id")]
    source_hash: Annotated[str, FromParent(field="source_hash")]
    page_count: Annotated[int | None, FromParent(field="page_count", required=False)]


class IngestStageParseStepParseOutput(NodeOutput):
    """
    Output of the parse step.

    Attributes:
        ir (DocumentIR): The canonical IR (parser-produced, or the degraded empty IR), with the parse
            ChainTrace stamped when a chain ran.
        degraded (bool): True when no parse was produced (no PDF view, or the chain exhausted under
            ``failure_policy=continue``) — the figure-render and markdown steps skip their work.
    """

    ir: DocumentIR
    degraded: bool


__all__ = ["IngestStageParseStepParseInput", "IngestStageParseStepParseOutput"]
