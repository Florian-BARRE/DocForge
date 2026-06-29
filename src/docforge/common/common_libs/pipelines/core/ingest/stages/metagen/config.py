# ====== Code Summary ======
# IngestStageMetagenConfig — the per-collection pure-setting knobs of the metagen stage, co-located
# with the node and declared as its ``Config``. It controls only the GENERATION BUDGET and CONCURRENCY
# of the LLM metadata pass; the WHAT-to-generate (the per-field targets + their resolved types) is
# derived by the assembler from the collection's metadata schema and injected separately, and the LLM
# provider chain is an injected service. Every field carries a ``description`` so the discovery API
# renders a labelled form with zero hardcoded text. Frozen + strict (inherited from StageConfigBase):
# an out-of-contract value fails fast at assembly.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from common_libs.pipelines import StageConfigBase


class IngestStageMetagenConfig(StageConfigBase):
    """
    Metagen stage configuration — generation budget + concurrency knobs.

    These are the stage's pure-setting knobs (plain values, no provider wiring). The generation
    targets and their resolved field types are derived by the assembler from the collection's
    metadata schema, and the LLM chain is an injected service; neither is configured here.

    Attributes:
        max_concurrency (int): Maximum concurrent chunk-scope LLM calls.
        max_budget_usd (float): Estimated-cost cap per document (0 = unlimited).
    """

    max_concurrency: int = Field(
        default=8,
        ge=1,
        le=64,
        description=(
            "Maximum number of chunk-scope LLM calls run concurrently. Higher values speed up "
            "generation on large documents at the cost of more simultaneous provider load."
        ),
    )
    max_budget_usd: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Estimated-cost ceiling (USD) for the whole metadata pass on a single document. The "
            "budget gate skips generation once the projected spend would exceed it; 0 = unlimited."
        ),
    )


__all__ = ["IngestStageMetagenConfig"]
