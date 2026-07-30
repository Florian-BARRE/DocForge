# ====== Code Summary ======
# BaseParserNode — the abstract base of every parser alternative. It fixes the I/O (ParserConsumes →
# ParserProduces) and owns the shared shell: take the PDF bytes from the input, delegate to the
# engine-specific _parse, score the resulting IR, and degrade cleanly to an empty IR when there is no
# PDF view. A parser needs nothing but its config + input — no injected clients. Each concrete parser
# (Docling first) implements ONLY _parse, using its own engine, so it stays interchangeable.

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import DocumentIR, IntakeResult

# ====== Local Project Imports ======
from .io import ParserConsumes, ParserProduces


class BaseParserNode(ActionNode):
    """Abstract parser: homogeneous I/O + shared shell; children implement _parse with their engine."""

    Consumes = ParserConsumes
    Produces = ParserProduces

    @abstractmethod
    async def _parse(self, pdf_bytes: bytes, source: IntakeResult) -> DocumentIR:
        """Turn the PDF bytes into the canonical IR using the parser's own engine."""
        ...

    def _quality_score(self, ir: DocumentIR) -> float:
        """
        Default parse-quality heuristic — the share of blocks carrying extracted CONTENT.

        Text-bearing blocks and structured tables count as content; FIGURES deliberately do not —
        a scanned PDF parsed without OCR yields mostly image blocks, and that is exactly the low
        score the ScoreBelow gate escalates on. A table-heavy report is NOT a scan and must not
        trigger a pointless escalation. Children may override for a sharper metric.

        Args:
            ir (DocumentIR): The IR just produced by ``_parse``.

        Returns:
            float: Quality in [0, 1] (0 when the IR has no blocks).
        """
        if not ir.blocks:
            return 0.0
        with_content = sum(
            1
            for block in ir.blocks
            if (block.text and block.text.strip()) or block.table is not None
        )
        return with_content / len(ir.blocks)

    async def run(self, data: ParserConsumes) -> ParserProduces:
        """
        Delegate the PDF bytes to the parser engine and score the resulting IR.

        Degrades to an empty IR (score 0) when the source has no PDF view, so the escalation moves
        on and, if every parser degrades, the last empty IR is the stage output.

        Args:
            data (ParserConsumes): The resolved input carrying the IntakeResult.

        Returns:
            ParserProduces: The IR + its quality score.
        """
        source = data.source
        # 1. No convertible PDF view → degrade to an empty IR (score 0 → escalation moves on).
        if source.pdf_content is None:
            self.logger.warning(
                f"No PDF view for source '{source.source_hash}'; degrading to empty IR"
            )
            empty = DocumentIR(doc_id=source.source_hash, source_hash=source.source_hash)
            return ParserProduces(ir=empty, score=0.0)

        # 2. Delegate the bytes to the parser engine, then score the IR (the ScoreBelow gate reads it).
        ir = await self._parse(source.pdf_content, source)
        return ParserProduces(ir=ir, score=self._quality_score(ir))


__all__ = ["BaseParserNode"]
