# ====== Code Summary ======
# The PaddleOCR-VL 1.6 parser node — a NETWORK client, not an in-process engine. It POSTs the PDF bytes
# to a sidecar (src/paddle_server, POST /vl-parse) that runs the PaddleOCR-VL 1.6 vision-language
# layout-parsing pipeline on its own PaddlePaddle runtime, and maps the sidecar's clean per-page block
# contract into the canonical IR via PaddleOcrVlIRMapper. Subclasses SidecarParserNode, which owns the
# sidecar HTTP call and preflight: this class declares ONLY its registry identity, its Config, its
# ENDPOINT and its mapper. Wire it as an OFF-by-default ScoreBelow escalation head after standard
# docling, never in the default/light blob — the sidecar's VLM is heavy, slow and optional (built lazily
# sidecar-side).

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..sidecar_base import SidecarParserNode
from .config import ParserPaddleOcrVlConfig
from .mapper import PaddleOcrVlIRMapper


@NodeRegistry.register("parser")
class ParserPaddleOcrVlNode(SidecarParserNode):
    """
    Parse a PDF with the PaddleOCR-VL 1.6 sidecar, mapping its layout-parsing output to the canonical IR.

    A SOTA vision-language layout parser running on a separate PaddlePaddle sidecar, so the worker
    gains ZERO new deps — this node is a pure httpx client. PDF-only: with no PDF view the base
    degrades to an empty IR (score 0), the correct behaviour for an escalation step. Tables arrive as
    HTML the mapper flattens into a grid; formulas as LaTeX; figures as empty placeholders the
    figure_render stage crops from the normalized bbox.
    """

    KIND = "paddleocr_vl"
    NAME = "PaddleOCR-VL 1.6"
    SUMMARY = "Parse a PDF into the canonical IR with the PaddleOCR-VL 1.6 sidecar (PaddleOCR)."
    HOW_IT_WORKS = (
        "POSTs the PDF bytes to the PaddleOCR-VL 1.6 sidecar (a vision-language layout-parsing "
        "pipeline on its own PaddlePaddle runtime), which returns one reading-ordered block list per "
        "page with tables as HTML and formulas as LaTeX already inlined. The node maps that into the "
        "DocumentIR — pixel bboxes normalized against the rendered page dims (top-left origin, no "
        "y-flip), tables flattened to a grid, figures left as empty crop placeholders. The sidecar's "
        "VLM is heavy, slow and built lazily: wire this as an OFF-by-default score_below escalation "
        "head after standard docling."
    )
    Config = ParserPaddleOcrVlConfig
    ENDPOINT = "/vl-parse"
    MAPPER = PaddleOcrVlIRMapper

    def _query_params(self) -> dict[str, bool]:
        """Forward the enabled sub-pipelines to the sidecar as query params."""
        config: ParserPaddleOcrVlConfig = self.config
        return {
            "use_chart_recognition": config.use_chart_recognition,
            "use_seal_recognition": config.use_seal_recognition,
            "use_ocr_for_image_block": config.use_ocr_for_image_block,
        }


__all__ = ["ParserPaddleOcrVlNode"]
