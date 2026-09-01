# ====== Code Summary ======
# PdfProbeNode — reads the PDF view's SYSTEM facts: the page count, with loud, clear failures
# on encrypted or corrupt PDFs (never a cryptic pypdf traceback). It also owns the one policy the
# page count enables: a page-count admission ceiling (``max_pages``) that rejects an over-large
# document HERE — the earliest point the count is known — BEFORE the expensive parse/OCR ever runs
# (the cheap mitigation for a runaway CPU parse). Deciding what a non-text zone IS (scanned text /
# logo / photo / chart) still happens at the finest grain — per IR block, in the enrich stage —
# never here. Degrades to an empty probe when there is no PDF view.

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
    """The one policy the page count enables: the page-count admission ceiling."""

    max_pages: int = Field(
        default=2000,
        ge=0,
        description=(
            "Reject a document whose PDF view exceeds this many pages, BEFORE the expensive "
            "parse/OCR runs — the cheap guard against a runaway parse. 0 disables the ceiling "
            "(no cap). Defaults to 2000."
        ),
    )


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
        "traceback. A document over the ``max_pages`` ceiling is rejected here — the earliest "
        "point the page count is known — so an over-large document never reaches parse/OCR. What "
        "each non-text zone IS (scanned text, logo, photo…) is decided per IR block by the enrich "
        "stage — not here."
    )
    Config = PdfProbeConfig

    Consumes = PdfProbeConsumes
    Produces = PdfProbeProduces

    async def run(self, data: PdfProbeConsumes) -> PdfProbeProduces:
        """
        Inspect the PDF view (empty probe when there is none).

        Raises:
            ValueError: When the PDF is password-protected or unreadable, or when its page count
                exceeds the ``max_pages`` ceiling (clear message naming the count and the limit).
        """
        config: PdfProbeConfig = self.config

        # 1. No PDF view → nothing to probe (0 pages, cannot breach the cap); the parser degrades.
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

        # 3. Admission ceiling: reject an over-large document BEFORE parse/OCR spend. A 0 cap
        #    disables the check (escape hatch). The message names the actual count and the limit so
        #    ``job.error`` tells the operator exactly why the document was rejected.
        if config.max_pages and page_count > config.max_pages:
            raise ValueError(
                f"document has {page_count} pages, exceeds the collection's "
                f"max_pages={config.max_pages}"
            )

        # 4. Report the facts.
        self.logger.debug(f"PDF probe: {page_count} pages")
        return PdfProbeProduces(probe=PdfProbe(page_count=page_count))


__all__ = ["PdfProbeNode", "PdfProbeConfig"]
