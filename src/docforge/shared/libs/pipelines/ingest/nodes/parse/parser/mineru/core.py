# ====== Code Summary ======
# The MinerU2.5-Pro parser node — a NETWORK client, not an in-process engine. It POSTs the PDF bytes to
# a sidecar (src/mineru_server, POST /parse) that runs the MinerU2.5-Pro vision-language layout-parsing
# pipeline on its own torch+CUDA runtime, and maps the sidecar's clean per-page block contract into the
# canonical IR via MineruIRMapper. Subclasses SidecarParserNode, which owns the sidecar HTTP call and
# preflight: this class declares ONLY its registry identity, its Config, its ENDPOINT and its mapper.
# Wire it as an OFF-by-default ScoreBelow escalation head after standard docling, never in the
# default/light blob — the sidecar's VLM is GPU-only, heavy, slow and optional (built lazily sidecar-
# side).

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..sidecar_base import SidecarParserNode
from .config import ParserMineruConfig
from .mapper import MineruIRMapper


@NodeRegistry.register("parser")
class ParserMineruNode(SidecarParserNode):
    """
    Parse a PDF with the MinerU2.5-Pro sidecar, mapping its layout-parsing output to the canonical IR.

    A SOTA vision-language layout parser (OmniDocBench 95.69) running on a separate torch+CUDA sidecar,
    so the worker gains ZERO new deps — this node is a pure httpx client. PDF-only: with no PDF view the
    base degrades to an empty IR (score 0), the correct behaviour for an escalation step. Tables arrive
    as HTML the mapper flattens into a grid; formulas as LaTeX; figures as empty placeholders the
    figure_render stage crops from the normalized bbox.
    """

    KIND = "mineru"
    NAME = "MinerU2.5-Pro"
    SUMMARY = "Parse a PDF into the canonical IR with the MinerU2.5-Pro VLM sidecar."
    HOW_IT_WORKS = (
        "POSTs the PDF bytes to the MinerU2.5-Pro sidecar (a vision-language layout-parsing pipeline "
        "on its own torch+CUDA runtime, GPU-only), which returns one reading-ordered block list per "
        "page with tables as HTML and formulas as LaTeX already inlined. The node maps that into the "
        "DocumentIR — bboxes normalized against the page dims (top-left origin, no y-flip), tables "
        "flattened to a grid, figures left as empty crop placeholders. The sidecar's VLM is heavy, "
        "slow and built lazily: wire this as an OFF-by-default score_below escalation head after "
        "standard docling."
    )
    Config = ParserMineruConfig
    ENDPOINT = "/parse"
    MAPPER = MineruIRMapper

    def _query_params(self) -> None:
        """This sidecar's /parse endpoint takes no sub-pipeline query params."""
        return None


__all__ = ["ParserMineruNode"]
