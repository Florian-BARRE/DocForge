# ====== Code Summary ======
# IO contract for the ingest stage: its input is read from the pipeline run input (the original
# bytes / filename / optional doc id); its output is the assembled result of its three steps
# (addressing + PDF view + probe), the artefact every downstream stage of the ingest pipeline reads.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromRunInput, NodeInput, NodeOutput


class IngestStageIngestInput(NodeInput):
    """
    Input of the ingest stage (read from the pipeline run input).

    Attributes:
        original_bytes (bytes): The raw original file bytes.
        filename (str): The original filename.
        doc_id (str | None): A pre-assigned document id, or None to mint a fresh one.
    """

    original_bytes: Annotated[bytes, FromRunInput()]
    filename: Annotated[str, FromRunInput()]
    doc_id: Annotated[str | None, FromRunInput(required=False)]


class IngestStageIngestOutput(NodeOutput):
    """
    Output of the ingest stage — the assembled result of its three steps.

    Attributes:
        doc_id (str): The effective document id.
        source_hash (str): SHA-256 content address of the original.
        original_format (str): Original file format (lowercase, no dot).
        original_key (str): Object-store key of the original.
        pdf_key (str | None): Object-store key of the PDF view, or None.
        converted (bool): True when an actual office/HTML -> PDF conversion happened.
        page_count (int | None): Page count of the converted PDF, or None.
        needs_ocr (bool): True when downstream parsing must OCR.
        media_type (str): Canonical MIME type of the document.
        implicit_meta (dict): File-intrinsic metadata (lowest-precedence layer of doc_meta).
    """

    doc_id: str
    source_hash: str
    original_format: str
    original_key: str
    pdf_key: str | None
    converted: bool
    page_count: int | None
    needs_ocr: bool
    media_type: str
    implicit_meta: dict = {}


__all__ = ["IngestStageIngestInput", "IngestStageIngestOutput"]
