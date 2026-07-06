# ====== Code Summary ======
# PdfProbeNode — reads the PDF view's SYSTEM facts: the page count, with loud, clear failures
# on encrypted or corrupt PDFs (never a cryptic pypdf traceback). Nothing more: deciding what a
# non-text zone IS (scanned text / logo / photo / chart) happens at the finest grain — per IR
# block, in the enrich stage — never here. Degrades to an empty probe when there is no PDF view.

# ====== Standard Library Imports ======
import io

# ====== Third-Party Library Imports ======
from pydantic import Field
from pypdf import PdfReader

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import PdfProbe, PdfView


class PdfProbeConfig(NodeConfig):
    """No knobs — the probe reads objective facts off the PDF."""


class PdfProbeConsumes(NodeInput):
    """The PDF view to inspect."""

    pdf: PdfView = Field(description="The converted working PDF to inspect.")


class PdfProbeProduces(NodeOutput):
    """The PDF's system facts."""

    probe: PdfProbe = Field(description="System facts of the PDF (page count).")


@NodeRegistry.register("intake")
class PdfProbeNode(ActionNode):
    """Read the PDF view's system facts (page count), failing clearly on unreadable PDFs."""

    KIND = "pdf_probe"
    UNIQUE_IN_GRAPH = True
    NAME = "PDF probe"
    SUMMARY = "Read the PDF's system facts (page count); fail clearly on unreadable PDFs."
    HOW_IT_WORKS = (
        "Opens the PDF and counts the pages. An encrypted PDF is tried with the empty user "
        "password, then rejected with a clear message; a corrupt PDF never leaks a parser "
        "traceback. What each non-text zone IS (scanned text, logo, photo…) is decided per IR "
        "block by the enrich stage — not here."
    )
    Config = PdfProbeConfig

    Consumes = PdfProbeConsumes
    Produces = PdfProbeProduces

    async def run(self, data: PdfProbeConsumes) -> PdfProbeProduces:
        """
        Inspect the PDF view (empty probe when there is none).

        Raises:
            ValueError: When the PDF is password-protected or unreadable (clear message).
        """
        # 1. No PDF view → nothing to probe; the parser will degrade downstream.
        if data.pdf.content is None:
            self.logger.warning(f"No PDF view to probe; emitting an empty probe")
            return PdfProbeProduces(probe=PdfProbe())

        # 2. Open the PDF with CLEAR failures: encrypted → try the empty user password (many PDFs
        #    are owner-locked only), else fail loudly; a corrupt body never leaks a pypdf traceback.
        try:
            reader = PdfReader(io.BytesIO(data.pdf.content))
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("the PDF is password-protected and cannot be read")
            page_count = len(reader.pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"unreadable PDF: {exc}") from exc

        # 3. Report the facts.
        self.logger.debug(f"PDF probe: {page_count} pages")
        return PdfProbeProduces(probe=PdfProbe(page_count=page_count))


__all__ = ["PdfProbeNode", "PdfProbeConfig"]
