# ====== Code Summary ======
# BaseConverterNode — the abstract base of every converter. It fixes the I/O (ConverterConsumes →
# ConverterProduces) and owns the shared shell: a source that already IS a PDF passes through
# untouched, anything else is delegated to the engine-specific _convert, and a non-convertible
# format degrades to an empty PdfView (the parser downstream degrades in turn). Children implement
# ONLY _convert with their own engine (Gotenberg first).

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

    async def run(self, data: ConverterConsumes) -> ConverterProduces:
        """
        Produce the canonical PDF view.

        Args:
            data (ConverterConsumes): The source and its detected nature.

        Returns:
            ConverterProduces: The PDF view (pass-through, converted, or empty when degraded).
        """
        # 1. Already a PDF — the original bytes ARE the canonical view.
        if data.probe.format == "pdf":
            return ConverterProduces(pdf=PdfView(content=data.source.content))

        # 2. Delegate to the engine; None means the format has no PDF view (degrade downstream).
        converted = await self._convert(data.source, data.probe)
        if converted is None:
            self.logger.warning(
                f"'{data.source.filename}' ({data.probe.format}) has no PDF conversion; degrading"
            )
        return ConverterProduces(pdf=PdfView(content=converted))


__all__ = ["BaseConverterNode"]
