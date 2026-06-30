# ====== Code Summary ======
# The parse stage — an ESCALATION over its parser candidates (the clean replacement for the old parser
# chain). Its candidates are wired by ``score_below`` transitions: the first parser whose quality score
# clears the acceptance threshold wins and its IR is the stage output; a parser that scores too low (or
# fails) escalates to the next. The candidate list + threshold are what the builder fills from the
# per-collection config — so a collection chooses its parsers and how strict the acceptance is.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import (
    Condition,
    FromNode,
    GroupNode,
    NodeInput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import ParserNode, ParserOutput


class ParseStageInput(NodeInput):
    """The parse stage input — the PDF view + identity produced by the ingest stage."""

    source_hash: Annotated[str, FromNode("ingest", "source_hash")]
    pdf_key: Annotated[str | None, FromNode("ingest", "pdf_key")]
    needs_ocr: Annotated[bool, FromNode("ingest", "needs_ocr")]


class ParseStage(GroupNode):
    """Parse: try parser candidates in order until one's quality clears the acceptance threshold."""

    Input = ParseStageInput
    Output = ParserOutput  # the accepted (terminal) parser's output is the stage output

    def __init__(self, parsers: list[ParserNode], accept_threshold: float = 0.8) -> None:
        """
        Wire the parser candidates as an escalation (``score_below`` edges between consecutive ones).

        Args:
            parsers (list[ParserNode]): The ordered parser candidates (index 0 is tried first).
            accept_threshold (float): Minimum quality score to accept a parser (else escalate).
        """
        # 1. Each parser escalates to the next when its score is below the acceptance threshold.
        transitions = [
            Transition(parsers[i].id, parsers[i + 1].id, Condition.SCORE_BELOW, accept_threshold)
            for i in range(len(parsers) - 1)
        ]
        super().__init__("parse", parsers, transitions)


__all__ = ["ParseStage", "ParseStageInput"]
