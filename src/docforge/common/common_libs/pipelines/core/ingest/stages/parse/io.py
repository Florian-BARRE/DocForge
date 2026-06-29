# ====== Code Summary ======
# IO contract for the parse stage: its input is read from the ingest stage's output (the content
# address, the PDF view key, page count, doc id, and the OCR fork flag) via FromSibling; its output is
# the canonical IR plus the assembled ParseResult (markdown key + figure crop keys), the artefacts
# every downstream stage of the ingest pipeline reads.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .result import ParseResult


class IngestStageParseInput(NodeInput):
    """
    Input of the parse stage (read from the ingest stage's output).

    Attributes:
        source_hash (str): SHA-256 content address of the original (from ingest).
        pdf_key (str | None): Object-store key of the PDF view, or None when there is no PDF.
        page_count (int | None): Page count of the PDF view, or None when there is no PDF.
        doc_id (str): The effective document id (from ingest).
        needs_ocr (bool): True when downstream parsing must OCR (carried through for lineage).
    """

    source_hash: Annotated[str, FromSibling(producer="ingest", field="source_hash")]
    pdf_key: Annotated[
        str | None, FromSibling(producer="ingest", field="pdf_key", required=False)
    ]
    page_count: Annotated[
        int | None, FromSibling(producer="ingest", field="page_count", required=False)
    ]
    doc_id: Annotated[str, FromSibling(producer="ingest", field="doc_id")]
    needs_ocr: Annotated[bool, FromSibling(producer="ingest", field="needs_ocr")]


class IngestStageParseOutput(NodeOutput):
    """
    Output of the parse stage — the canonical IR and the assembled parse artefacts.

    Attributes:
        ir (DocumentIR): The canonical IR (parse trace stamped, figure crop keys patched).
        parse_result (ParseResult): The durable artefact (IR + markdown key + figure crop keys).
    """

    ir: DocumentIR
    parse_result: ParseResult


__all__ = ["IngestStageParseInput", "IngestStageParseOutput"]
