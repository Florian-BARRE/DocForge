# ====== Code Summary ======
# The ingest-stage artefacts, in pipeline order: SourceProbe (what the bytes really are — content
# sniffing, never trust the extension), PdfView (the canonical PDF bytes after conversion, None
# when not convertible), PdfProbe (the PDF's system facts), and IntakeResult — the stage OUTPUT the
# parse stage consumes. NOTE: no scan flag here — what a non-text zone IS (scanned text / logo /
# photo / chart) is decided at the FINEST grain, per IR block, by the enrich stage.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact


class SourceProbe(Artifact):
    """What the uploaded bytes actually are — detected from content, not from the extension."""

    format: str = Field(description="Detected format token (pdf, docx, html, txt, …).")
    mime_type: str = Field(description="Detected MIME type.")
    file_size: int = Field(description="Size of the raw bytes.")


class PdfView(Artifact):
    """The canonical PDF view of the source; content is None when the source is not convertible."""

    content: bytes | None = Field(
        default=None, description="PDF bytes (the original bytes when the source already is a PDF)."
    )
    preview_content: bytes | None = Field(
        default=None,
        description="A view-ONLY PDF that must NOT feed the parser — set for structured text "
        "formats (html/md) parsed natively, so they still get page renders and a viewable PDF. "
        "Distinct from content, which the parser consumes.",
    )


class PdfProbe(Artifact):
    """System facts read from the PDF view."""

    page_count: int = Field(default=0, description="Total page count (0 when there is no PDF).")


class IntakeResult(Artifact):
    """An ingested source, ready to parse — its identity, PDF bytes and system facts."""

    source_hash: str = Field(description="Content-addressing hash of the original file bytes.")
    source_format: str = Field(
        default="",
        description="Detected source format token (pdf, html, md, docx…); lets a parser handle a "
        "structured text format (html/md) from its ORIGINAL bytes instead of a PDF round-trip.",
    )
    source_content: bytes | None = Field(
        default=None,
        description="The ORIGINAL uploaded bytes — parsed natively by structure-aware formats "
        "(html/md) whose PDF round-trip would flatten their heading tree.",
    )
    pdf_content: bytes | None = Field(
        default=None,
        description="The PDF-view bytes to parse; None when the source is not convertible or is "
        "parsed natively from its original bytes.",
    )
    preview_pdf: bytes | None = Field(
        default=None,
        description="A PDF produced ONLY for viewing (never fed to the parser); set for structured "
        "text formats (html/md) that are parsed natively yet still deserve a page render + a "
        "viewable PDF. Distinct from pdf_content, which the parser consumes.",
    )
    page_count: int = Field(default=0, description="Total page count of the PDF view.")


__all__ = ["SourceProbe", "PdfView", "PdfProbe", "IntakeResult"]
