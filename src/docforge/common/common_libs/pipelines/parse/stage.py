# ====== Code Summary ======
# The parse stage — a SEQUENCE wrapping the parser escalation and the two artefact nodes that turn the
# winning IR into the durable document views: ``select`` (the parser escalation sub-group) ->
# ``figure_render`` (crop + upload figures, patch the IR) -> ``markdown`` (serialise + upload the
# markdown view). Its typed Output assembles the final IR + the markdown view key + the figure crop
# keys — the artefacts every downstream stage (enrich/chunk) and the worker node-cache persist read.
# The escalation lives in its own sub-group so the artefact nodes can bind to the winner's IR
# statically; the candidate list + acceptance threshold are filled by the builder.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines.flow import (
    FromNode,
    GroupNode,
    NodeInput,
    NodeOutput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import ParseFigureRender, ParseMarkdown, ParserNode
from .select import ParseSelect


class ParseStageInput(NodeInput):
    """The parse stage input — the PDF view + identity produced by the ingest stage."""

    source_hash: Annotated[str, FromNode("ingest", "source_hash")]
    pdf_key: Annotated[str | None, FromNode("ingest", "pdf_key")]
    needs_ocr: Annotated[bool, FromNode("ingest", "needs_ocr")]


class ParseStageOutput(NodeOutput):
    """The assembled parse output — the canonical IR + the document views consumed downstream."""

    ir: DocumentIR
    markdown_key: str | None
    figure_crop_keys: dict[str, str]


class ParseStage(GroupNode):
    """Parse: escalate parsers, then render figure crops + the markdown view from the winning IR."""

    Input = ParseStageInput
    Output = ParseStageOutput

    def __init__(self, parsers: list[ParserNode], accept_threshold: float = 0.8) -> None:
        """
        Wire the escalation sub-group + the two artefact nodes as a sequence (``always`` edges).

        Args:
            parsers (list[ParserNode]): The ordered parser candidates (passed to the escalation).
            accept_threshold (float): Minimum quality score to accept a parser (else escalate).
        """
        super().__init__(
            "parse",
            [
                ParseSelect(parsers, accept_threshold),
                ParseFigureRender("figure_render"),
                ParseMarkdown("markdown"),
            ],
            [Transition("select", "figure_render"), Transition("figure_render", "markdown")],
        )

    def assemble(self, outputs: dict, terminal: NodeOutput) -> ParseStageOutput:
        """
        Assemble the stage output from the terminal markdown node (final IR + view artefacts).

        Args:
            outputs (dict): The child outputs by id (``select`` / ``figure_render`` / ``markdown``).
            terminal (NodeOutput): The markdown node output (the terminal of the sequence).

        Returns:
            ParseStageOutput: The final IR + the markdown view key + the figure crop keys.
        """
        return ParseStageOutput(
            ir=terminal.ir,
            markdown_key=terminal.markdown_key,
            figure_crop_keys=terminal.figure_crop_keys,
        )


__all__ = ["ParseStage", "ParseStageInput", "ParseStageOutput"]
