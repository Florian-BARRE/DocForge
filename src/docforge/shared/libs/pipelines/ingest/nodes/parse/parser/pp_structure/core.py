# ====== Code Summary ======
# The PP-StructureV3 (PaddleOCR) parser node — a NETWORK client, not an in-process engine. It POSTs the
# PDF bytes to a sidecar (src/paddle_server) that runs the PaddleX layout-parsing pipeline on its own
# PaddlePaddle runtime, and maps the sidecar's clean per-page block contract into the canonical IR via
# PpStructureIRMapper. Subclasses SidecarParserNode, which owns the sidecar HTTP call and preflight:
# this class declares ONLY its registry identity, its Config, its ENDPOINT and its mapper. Wire it as an
# OFF-by-default ScoreBelow escalation head after standard docling, never in the default/light blob —
# the sidecar is heavy and optional.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..sidecar_base import SidecarParserNode
from .config import ParserPpStructureConfig
from .mapper import PpStructureIRMapper


@NodeRegistry.register("parser")
class ParserPpStructureNode(SidecarParserNode):
    """
    Parse a PDF with the PP-StructureV3 sidecar, mapping its layout-parsing output to the canonical IR.

    A SOTA layout parser (Apache-2.0) running on a separate PaddlePaddle sidecar, so the worker gains
    ZERO new deps — this node is a pure httpx client. PDF-only: with no PDF view the base degrades to
    an empty IR (score 0), the correct behaviour for an escalation step. Tables arrive as HTML the
    mapper flattens into a grid; formulas as LaTeX; figures as empty placeholders the figure_render
    stage crops from the normalized bbox.
    """

    KIND = "pp_structure"
    NAME = "PP-StructureV3 (PaddleOCR)"
    SUMMARY = "Parse a PDF into the canonical IR with the PP-StructureV3 sidecar (PaddleOCR)."
    HOW_IT_WORKS = (
        "POSTs the PDF bytes to the PP-StructureV3 sidecar (a PaddleX layout-parsing pipeline on its "
        "own PaddlePaddle runtime), which returns one reading-ordered block list per page with tables "
        "as HTML and formulas as LaTeX already inlined. The node maps that into the DocumentIR — "
        "pixel bboxes normalized against the rendered page dims (top-left origin, no y-flip), tables "
        "flattened to a grid, figures left as empty crop placeholders. The sidecar is heavy and "
        "optional: wire this as an OFF-by-default score_below escalation head after standard docling."
    )
    Config = ParserPpStructureConfig
    ENDPOINT = "/layout-parsing"
    MAPPER = PpStructureIRMapper

    def _query_params(self) -> dict[str, bool]:
        """Forward the enabled sub-pipelines to the sidecar as query params."""
        config: ParserPpStructureConfig = self.config
        return {
            "use_table_recognition": config.use_table_recognition,
            "use_formula_recognition": config.use_formula_recognition,
            "use_seal_recognition": config.use_seal_recognition,
            "use_doc_orientation_classify": config.use_doc_orientation_classify,
            "use_doc_unwarping": config.use_doc_unwarping,
        }


__all__ = ["ParserPpStructureNode"]
