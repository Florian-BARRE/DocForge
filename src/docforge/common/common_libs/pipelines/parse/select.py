# ====== Code Summary ======
# ParseSelect — the parser ESCALATION sub-group of the parse stage. Its children are the parser
# candidates wired by ``score_below`` transitions: the first parser whose quality score clears the
# acceptance threshold wins and its output (the canonical IR + score) is the sub-group output; a
# parser that scores too low (or fails) escalates to the next. Isolating the escalation in its own
# group gives it a STABLE id (``select``) whose ``assemble`` returns the WINNING parser's output —
# so the downstream figure-render / markdown nodes bind to it statically (a flat escalation could not
# name the dynamically-chosen winner). The candidate list + threshold come from the builder.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import (
    Condition,
    FromGroupInput,
    GroupNode,
    NodeInput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import ParserNode, ParserOutput


class ParseSelectInput(NodeInput):
    """The escalation input — the PDF view + identity, read from the parse stage's input."""

    source_hash: Annotated[str, FromGroupInput()]
    pdf_key: Annotated[str | None, FromGroupInput()]
    needs_ocr: Annotated[bool, FromGroupInput()]


class ParseSelect(GroupNode):
    """Try parser candidates in order until one's quality clears the acceptance threshold."""

    Input = ParseSelectInput
    Output = ParserOutput  # the accepted (terminal) parser's output is the sub-group output

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
        super().__init__("select", parsers, transitions)


__all__ = ["ParseSelect", "ParseSelectInput"]
