# ====== Code Summary ======
# The dots.ocr parser node — a NETWORK client, not an in-process engine. It POSTs the PDF bytes to a
# sidecar (src/dots_ocr_server, POST /parse) that renders each page to an image, sends it to the
# dots.ocr per-element layout VLM (rednote-hilab/dots.ocr, served by vLLM on its own torch+CUDA
# runtime), and returns the shared per-page block contract, which DotsOcrIRMapper maps into the
# canonical IR. Subclasses SidecarParserNode, which owns the sidecar HTTP call and preflight: this class
# declares ONLY its registry identity, its Config, its ENDPOINT and its mapper. Wire it as an OFF-by-
# default ScoreBelow escalation head after standard docling, never in the default/light blob — the
# sidecar's VLM is GPU-only, heavy, slow and optional (built lazily sidecar-side).

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..sidecar_base import SidecarParserNode
from .config import ParserDotsOcrConfig
from .mapper import DotsOcrIRMapper


@NodeRegistry.register("parser")
class ParserDotsOcrNode(SidecarParserNode):
    """
    Parse a PDF with the dots.ocr sidecar, mapping its per-element layout output to the canonical IR.

    A compact (3B) per-element layout VLM (rednote-hilab/dots.ocr, MIT) running on a separate
    vLLM+CUDA sidecar, so the worker gains ZERO new deps — this node is a pure httpx client. PDF-only:
    with no PDF view the base degrades to an empty IR (score 0), the correct behaviour for an
    escalation step. Tables arrive as HTML the mapper flattens into a grid; formulas as LaTeX; figures
    (Picture) as empty placeholders the figure_render stage crops from the normalized bbox.
    """

    KIND = "dots_ocr"
    NAME = "dots.ocr"
    SUMMARY = "Parse a PDF into the canonical IR with the dots.ocr per-element layout VLM sidecar."
    HOW_IT_WORKS = (
        "POSTs the PDF bytes to the dots.ocr sidecar, which renders each page to an image and sends "
        "it to the dots.ocr layout VLM (rednote-hilab/dots.ocr, served by vLLM on its own torch+CUDA "
        "runtime, GPU-only). The sidecar returns one reading-ordered block list per page — the model's "
        "per-element categories normalized to labels, tables as HTML, formulas as LaTeX already "
        "inlined, bboxes divided by the rendered page-image dims. The node maps that into the "
        "DocumentIR (top-left origin, no y-flip; tables flattened to a grid; Picture left as an empty "
        "crop placeholder). The sidecar's VLM is heavy, slow and built lazily: wire this as an "
        "OFF-by-default score_below escalation head after standard docling."
    )
    Config = ParserDotsOcrConfig
    ENDPOINT = "/parse"
    MAPPER = DotsOcrIRMapper

    def _query_params(self) -> None:
        """This sidecar's /parse endpoint takes no sub-pipeline query params."""
        return None


__all__ = ["ParserDotsOcrNode"]
