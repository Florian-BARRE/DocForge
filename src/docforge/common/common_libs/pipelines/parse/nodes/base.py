# ====== Code Summary ======
# The parser-node contract — the shared base of every parser ALTERNATIVE in the parse escalation. A
# parser reads the PDF view produced by ingest, turns it into the canonical DocumentIR, and reports a
# QUALITY SCORE the escalation uses: a low score (or a failure) makes the stage escalate to the next
# parser via a score_below transition. The base factors the common shell (download the PDF / degrade
# cleanly when there is no PDF view); each concrete parser implements only ``_parse``. This is the clean
# replacement for the old parser "chain" — the candidates are nodes, the gate is a transition.

# ====== Standard Library Imports ======
from abc import abstractmethod
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models.document_ir import DocumentIR
from common_libs.pipelines.flow import ActionNode, Context, FromGroupInput, NodeInput, NodeOutput


class ParserInput(NodeInput):
    """Input of a parser node — read from the parse stage's input (the ingest result)."""

    source_hash: Annotated[str, FromGroupInput()]
    pdf_key: Annotated[str | None, FromGroupInput()]
    needs_ocr: Annotated[bool, FromGroupInput()]


class ParserOutput(NodeOutput):
    """Output of a parser node — the canonical IR + a quality score (drives the escalation)."""

    ir: DocumentIR
    score: float


class ParserNode(ActionNode):
    """
    Shared base of a parser alternative — downloads the PDF view, then delegates to ``_parse``.

    With no PDF view (a non-convertible original) the parser DEGRADES to an empty IR with score 0, so
    the escalation moves on; if every parser degrades, the last one's empty IR is the stage output.
    """

    Input = ParserInput
    Output = ParserOutput

    async def execute(self, ctx: Context) -> ParserOutput:
        """
        Download the PDF view and parse it (or degrade when there is none).

        Args:
            ctx (Context): The resolved parser input + the object store service.

        Returns:
            ParserOutput: The canonical IR + its quality score.
        """
        # 1. No PDF view -> degrade to an empty IR (score 0 so the escalation tries the next parser).
        if ctx.input.pdf_key is None:
            return ParserOutput(ir=self._empty_ir(ctx.input.source_hash), score=0.0)

        # 2. Fetch the PDF bytes and hand them to the concrete parser.
        pdf_bytes = await ctx.service("object_store").download(ctx.input.pdf_key)
        return await self._parse(pdf_bytes, ctx.input)

    @staticmethod
    def _empty_ir(source_hash: str) -> DocumentIR:
        """Build the empty IR used on the degraded (no PDF view) path."""
        return DocumentIR(doc_id=source_hash, source_hash=source_hash, n_pages=0, language="und")

    @abstractmethod
    async def _parse(self, pdf_bytes: bytes, inp: ParserInput) -> ParserOutput:
        """
        Parse the PDF bytes into the canonical IR + a quality score.

        Args:
            pdf_bytes (bytes): The PDF view of the document.
            inp (ParserInput): The resolved parser input (source_hash / needs_ocr).

        Returns:
            ParserOutput: The IR + its quality score (low -> the stage escalates to the next parser).
        """
        ...


__all__ = ["ParserNode", "ParserInput", "ParserOutput"]
