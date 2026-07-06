# ====== Code Summary ======
# The fixed I/O contract shared by EVERY parser: it consumes one IntakeResult (a reference to the
# source) and produces the canonical IR plus a quality score. Homogenising these two faces is the
# whole point of the base — a parser is interchangeable behind them, whatever engine it runs inside.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, ScoredOutput
from shared_libs.public_models import DocumentIR, IntakeResult


class ParserConsumes(NodeInput):
    """Input of any parser — the ingest result (the source reference to parse)."""

    source: IntakeResult = Field(description="The intake output (the working PDF to parse).")


class ParserProduces(ScoredOutput):
    """Output of any parser — the canonical IR + a quality score that drives the escalation."""

    ir: DocumentIR = Field(
        description="The parsed structure: blocks, tables, figures, heading tree."
    )


__all__ = ["ParserConsumes", "ParserProduces"]
