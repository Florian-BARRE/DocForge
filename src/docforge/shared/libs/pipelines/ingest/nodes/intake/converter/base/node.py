# ====== Code Summary ======
# BaseConverterNode — the abstract base of every converter. It fixes the I/O (ConverterConsumes →
# ConverterProduces) and owns the shared shell: a source that already IS a PDF passes through
# untouched, anything else is delegated to the engine-specific _convert, and a non-convertible
# format degrades to an empty PdfView (the parser downstream degrades in turn). Children implement
# ONLY _convert with their own engine (Gotenberg first). A SECOND, decoupled channel — _preview —
# lets an engine emit a view-only PDF for a format parsed natively (html/md): it rides on the same
# PdfView (preview_content) but never feeds the parser, so structure-aware formats keep their native
# parse yet still gain page renders and a viewable PDF downstream.

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import PdfView, SourceDocument, SourceProbe

# ====== Local Project Imports ======
from .io import ConverterConsumes, ConverterProduces


class BaseConverterNode(ActionNode):
    """Abstract converter: homogeneous I/O + shared shell; children implement _convert."""

    Consumes = ConverterConsumes
    Produces = ConverterProduces

    @abstractmethod
    async def _convert(self, source: SourceDocument, probe: SourceProbe) -> bytes | None:
        """Convert the source bytes to PDF with the converter's engine (None = not convertible)."""
        ...

    async def _preview(self, source: SourceDocument, probe: SourceProbe) -> bytes | None:
        """A view-ONLY PDF for a natively-parsed format (html/md); None by default (no preview)."""
        return None

    async def run(self, data: ConverterConsumes) -> ConverterProduces:
        """
        Produce the canonical PDF view (and, for natively-parsed formats, a view-only preview).

        Args:
            data (ConverterConsumes): The source and its detected nature.

        Returns:
            ConverterProduces: The PDF view (pass-through, converted, or empty when degraded); a
            preview PDF rides alongside it for formats that carry no parser PDF yet deserve a render.
        """
        # 1. Already a PDF — the original bytes ARE the canonical view (feeds parse AND render).
        if data.probe.format == "pdf":
            return ConverterProduces(pdf=PdfView(content=data.source.content))

        # 2. Delegate to the engine; None means the format has no PARSER PDF. A natively-parsed
        #    format (html/md) may still get a view-only preview via _preview — the two channels are
        #    decoupled, so the parser stays native while the render/view still gets its pages.
        converted = await self._convert(data.source, data.probe)
        preview = await self._preview(data.source, data.probe)
        if converted is None and preview is None:
            self.logger.warning(
                f"'{data.source.filename}' ({data.probe.format}) has no PDF conversion; degrading"
            )
        return ConverterProduces(pdf=PdfView(content=converted, preview_content=preview))


__all__ = ["BaseConverterNode"]
