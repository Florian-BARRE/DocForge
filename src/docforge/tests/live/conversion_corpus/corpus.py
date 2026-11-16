# ====== Code Summary ======
# The reference documents of the conversion corpus. Each entry names a stable key (the snapshot
# key), the file and the conversion path it exercises. Adding a document means adding an entry here
# and re-recording the snapshot.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from pathlib import Path

LIVE_DIR = Path(__file__).resolve().parent.parent
PDF_FIXTURES = LIVE_DIR.parent / "units" / "nodes" / "fixtures" / "pdf"
OWN_FIXTURES = LIVE_DIR / "fixtures"


@dataclass(frozen=True)
class CorpusDocument:
    """One reference document of the corpus.

    Attributes:
        key: Stable snapshot key.
        path: The file ingested.
        mime_type: Declared upload content type.
        exercises: The conversion path this document is here to cover (documentation only).
    """

    key: str
    path: Path
    mime_type: str
    exercises: str

    @property
    def extension(self) -> str:
        return self.path.suffix.lstrip(".").lower()

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


CONVERSION_CORPUS: tuple[CorpusDocument, ...] = (
    CorpusDocument(
        key="pdf_native_contract",
        path=PDF_FIXTURES / "contrat_natif.pdf",
        mime_type="application/pdf",
        exercises="native-text multi-page PDF: pdf_probe (pypdf), docling parse, structure chunking",
    ),
    CorpusDocument(
        key="pdf_scanned_image_only",
        path=PDF_FIXTURES / "scanned_image_only.pdf",
        mime_type="application/pdf",
        exercises="image-only PDF: no text layer, pdfium page render, OCR path",
    ),
    CorpusDocument(
        key="pdf_text_layer_metadata",
        path=PDF_FIXTURES / "text_layer_with_metadata.pdf",
        mime_type="application/pdf",
        exercises="tiny text-layer PDF with document-info metadata (pypdf metadata read)",
    ),
    CorpusDocument(
        key="docx_memo",
        path=OWN_FIXTURES / "conversion_memo.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        exercises="Office document: Gotenberg (LibreOffice) to PDF, then the PDF path; heading + table",
    ),
    CorpusDocument(
        key="png_text_image",
        path=OWN_FIXTURES / "text_image.png",
        mime_type="image/png",
        exercises="plain image: Gotenberg image to PDF, then OCR of the rendered page",
    ),
)
