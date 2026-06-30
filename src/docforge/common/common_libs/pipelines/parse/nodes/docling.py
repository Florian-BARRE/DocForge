# ====== Code Summary ======
# DoclingParse — the Docling parser as a clean ActionNode candidate of the parse escalation. It wraps
# the Docling backend (lazy-imported: heavy native deps) and reports the IR's quality score so the
# escalation can decide whether to accept it or try the next parser. ``use_gpu`` is a DEPLOYMENT default
# (resolved from RUNTIME_CONFIG at build time and passed in by the builder) — NOT a hardcoded value and
# NOT a per-collection knob; there is no endpoint to configure (Docling runs in-process).

# ====== Internal Project Imports ======
from common_libs.pipelines.parse.nodes.base import ParserInput, ParserNode, ParserOutput


class DoclingParse(ParserNode):
    """Parse the PDF view with the Docling backend; the IR's quality score drives the escalation."""

    def __init__(self, node_id: str = "docling", use_gpu: bool = False) -> None:
        """
        Args:
            node_id (str): The node id (default ``"docling"``).
            use_gpu (bool): Deployment GPU flag (resolved from RUNTIME_CONFIG by the builder).
        """
        super().__init__(node_id)
        self._use_gpu = use_gpu

    async def _parse(self, pdf_bytes: bytes, inp: ParserInput) -> ParserOutput:
        """
        Parse the PDF bytes into the canonical IR + its quality score.

        Args:
            pdf_bytes (bytes): The PDF view of the document.
            inp (ParserInput): The resolved parser input (source_hash drives the IR identity).

        Returns:
            ParserOutput: The Docling IR + its quality score (low -> the stage escalates).
        """
        # 1. Lazy import — Docling pulls heavy native models, only loaded when a parse actually runs.
        from common_libs.providers.parser.docling.core import DoclingBackend

        # 2. Parse the PDF into the IR; its quality_score is the escalation signal (default 1.0).
        backend = DoclingBackend(use_gpu=self._use_gpu)
        ir = await backend.parse(
            pdf_bytes=pdf_bytes, doc_id=inp.source_hash, source_hash=inp.source_hash
        )
        score = ir.quality_score if ir.quality_score is not None else 1.0
        return ParserOutput(ir=ir, score=score)


__all__ = ["DoclingParse"]
