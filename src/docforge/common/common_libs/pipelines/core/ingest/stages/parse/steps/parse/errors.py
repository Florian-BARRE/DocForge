# ====== Code Summary ======
# The parse step's own failure type — raised when the parser chain is exhausted under
# ``failure_policy="raise"`` (every parser provider escalated or raised, so no IR was produced). The
# engine wraps the raw ``ChainExhaustedError`` in this typed error so the feedback tree carries a
# precise, parse-specific code.

# ====== Local Project Imports ======
from ..base import IngestStageParseStepError


class IngestStageParseStepParseError(IngestStageParseStepError):
    """Raised when the parser chain produced no IR under ``failure_policy=raise``."""

    code = "parse_failed"
    description = "The parser chain produced no canonical IR (every provider escalated or raised)."


__all__ = ["IngestStageParseStepParseError"]
