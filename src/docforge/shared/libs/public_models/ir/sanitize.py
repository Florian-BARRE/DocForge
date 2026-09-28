# ====== Code Summary ======
# IrTextSanitizer — the single post-parse chokepoint that strips U+0000 from every text field a
# DocumentIR carries. Every parser (docling/mineru/pp_structure/dots_ocr/paddleocr_vl/granite) maps
# its own engine output into the same IR, so cleaning the IR here — instead of in each of the five
# mappers — keeps the canonical representation NUL-free before anything downstream (chunks, embeddings,
# search text, generated metadata) can inherit the poison. A NUL is never real content, so the IR is
# no longer byte-identical to the raw parser output after this pass — an accepted, deliberate loss.

# ====== Internal Project Imports ======
from ..sanitize import TextSanitizer

# ====== Local Project Imports ======
from .document import DocumentIR


class IrTextSanitizer:
    """Static, pure pass that strips U+0000 from every text field of a DocumentIR (in place)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IrTextSanitizer is a static-only class and cannot be instantiated.")

    @classmethod
    def clean(cls, ir: DocumentIR) -> DocumentIR:
        """
        Strip U+0000 from the IR's title and every block's text, table cells and figure slots.

        Mutates the IR in place (parsers hand ownership of a freshly built IR to this pass) and
        returns it for call-site convenience.

        Args:
            ir (DocumentIR): The IR just produced by a parser's ``_parse``.

        Returns:
            DocumentIR: The same IR with every text field NUL-free.
        """
        # 1. The document title.
        ir.title = TextSanitizer.strip_nul(ir.title)
        # 2. Every block's native text plus the content slots its type may carry.
        for block in ir.blocks:
            block.text = TextSanitizer.strip_nul(block.text)
            if block.table is not None:
                block.table.cells = TextSanitizer.strip_nul(block.table.cells)
            if block.figure is not None:
                figure = block.figure
                figure.ocr_text = TextSanitizer.strip_nul(figure.ocr_text)
                figure.description = TextSanitizer.strip_nul(figure.description)
                figure.data_table = TextSanitizer.strip_nul(figure.data_table)
        return ir


__all__ = ["IrTextSanitizer"]
