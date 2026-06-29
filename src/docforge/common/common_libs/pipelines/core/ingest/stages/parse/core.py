# ====== Code Summary ======
# IngestStageParse — the parse stage of the ingest pipeline (StageKey.PARSE). It assembles its four
# steps (fetch_pdf -> parse -> figure_render -> markdown; the engine derives that order from their
# input bindings) and aggregates their outputs into the single IngestStageParseOutput (the canonical
# IR + the ParseResult) consumed downstream. NODE_CACHED: the whole stage is a Merkle node in the
# cache; ``fingerprint_params`` surfaces the parser chain signature for legacy cache parity.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec
from common_libs.pipelines.capabilities.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageParseContext
from .errors import IngestStageParseError
from .io import IngestStageParseInput, IngestStageParseOutput
from .steps import (
    IngestStageParseStepFetchPdf,
    IngestStageParseStepFigureRender,
    IngestStageParseStepMarkdown,
    IngestStageParseStepParse,
)


class IngestStageParse(IngestStageBase):
    """
    Parse stage — fetch the PDF view, parse it into the canonical IR, render figures, serialise md.

    Declares its four steps; the engine orders + runs them and the stage aggregates their outputs.
    Pinned to ``StageKey.PARSE`` + ``NODE_CACHED``; ``fingerprint_params`` returns the parser chain
    signature so the Merkle node-cache key tracks the parser providers/versions (legacy parity).
    """

    SPEC = StageSpec(
        key=StageKey.PARSE,
        name="Parse",
        description=(
            "Parse the PDF view into the canonical IR via the parser chain, render figure crops, "
            "and serialise the markdown view."
        ),
        cache_policy=CachePolicy.NODE_CACHED,
    )
    Input = IngestStageParseInput
    Output = IngestStageParseOutput
    Context = IngestStageParseContext
    Error = IngestStageParseError

    def __init__(self, parser_chain: "Chain[Any, Any]") -> None:
        """
        Wire the stage around the parser chain and build its four steps.

        Args:
            parser_chain (Chain[Any, Any]): Ordered parser escalation chain (docling, ...). Retained
                so the node fingerprint can reach the chain signature; the parse step resolves the
                same chain at runtime as the injected ``parser_chain`` service.
        """
        super().__init__()
        self._parser_chain = parser_chain
        self._steps = [
            IngestStageParseStepFetchPdf(),
            IngestStageParseStepParse(),
            IngestStageParseStepFigureRender(),
            IngestStageParseStepMarkdown(),
        ]

    @property
    def children(self) -> list:
        """The four parse steps (fetch_pdf -> parse -> figure_render -> markdown)."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageParseOutput:
        """
        Combine the step outputs into the stage output.

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageParseOutput: The canonical IR + the assembled ParseResult.
        """
        # 1. The markdown step holds both the final (patched) IR and the durable ParseResult.
        markdown = child_outputs["markdown"]

        # 2. Surface them as the single downstream-facing artefact.
        return IngestStageParseOutput(ir=markdown.ir, parse_result=markdown.parse_result)

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the parser chain signature as the node fingerprint params.

        Reproduces the legacy parse node-cache key exactly: any change to a parser provider/version
        invalidates the parse node. Read by the worker's fingerprint hook for NODE_CACHED stages.

        Returns:
            dict[str, Any]: ``{"parse_chain": <chain signature>}``.
        """
        return {"parse_chain": self._parser_chain.signature()}


__all__ = ["IngestStageParse"]
