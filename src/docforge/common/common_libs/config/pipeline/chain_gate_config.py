# ====== Code Summary ======
# ChainGateConfig — pure Pydantic model for chain escalation policy.
#
# Extracted here so ``libs/core/contracts/`` remains a leaf: it imports only
# standard-library and third-party packages, never other DocForge buckets.
# The runtime object (ChainGate) stays in libs/capabilities/chain_gate.py and
# imports this config from here.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ChainGateConfig(BaseModel):
    """
    Typed configuration for a chain's escalation policy.

    Attributes:
        min_score (float): Lower bound on the result's ``score()``.  An attempt whose
            score is strictly less than this triggers escalation.  A score of ``None``
            (unknown) never triggers escalation on its own.
        max_duration_ms (int | None): Soft upper bound on an attempt's wall-clock
            duration — surfaced in the UI for future enforcement; not enforced in
            Phase A.
    """

    min_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Escalate when the result's score is strictly below this threshold.",
    )
    max_duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Soft wall-clock budget per attempt (ms). Surfaced in UI; not enforced in Phase A.",
    )


__all__ = ["ChainGateConfig"]
