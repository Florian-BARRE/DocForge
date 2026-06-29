# ====== Code Summary ======
# ChainGateConfig — pure Pydantic model for chain escalation + exhaustion policy.
#
# Lives in ``common_libs/config/`` (a config-layer leaf): it imports only standard-library
# and third-party packages, never other DocForge buckets. The runtime object (ChainGate)
# lives in the chain brick ``common_libs/pipeline/bricks/chain/gate.py`` and imports this config
# from here.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class ChainGateConfig(BaseModel):
    """
    Typed configuration for a chain's escalation policy AND its exhaustion behaviour.

    The gate decides two distinct things:

    1. **Escalation** (per attempt) — when to move on to the next provider:
       ``min_score`` (result below threshold) and ``max_duration_ms`` (attempt too slow).
    2. **Failure policy** (on exhaustion) — what happens when NO provider was accepted:
       ``failure_policy`` (raise vs continue) + ``on_degraded`` (what "continue" yields).

    ``model_config`` uses ``extra="ignore"`` so gates serialized before these fields existed
    (and any since-removed knob such as ``max_cost_usd``) still load against the current model.

    Per-family score semantics — IMPORTANT:
        ``min_score`` is a single scalar, but the ``score()`` it gates means a DIFFERENT
        thing per provider family — there is no universal "quality" metric across stages:
          * parse (Docling) — block-coverage ratio (fraction of the page turned into IR blocks).
          * ocr — character-level recognition confidence (a genuine model-emitted 0-1 value).
          * vlm — structured-output validity (did the description / chart schema parse?).
        A given ``min_score`` is therefore only comparable WITHIN one family. This is why the
        defaults diverge: most stages use ``0.5`` (a neutral midpoint for ratio/validity
        heuristics), while the OCR gate defaults to ``0.85`` (see ``EnrichConfig.ocr_gate``).
        OCR's 0.85 is deliberate, not an accidental divergence: OCR confidence is a real,
        well-calibrated 0-1 metric, so a high bar correctly escalates a low-confidence local
        OCR result to a stronger provider. Do NOT "normalize" these defaults to one value —
        changing 0.85 alters OCR escalation behaviour.

    Attributes:
        min_score (float): Lower bound on the result's ``score()`` (see per-family note above).
            An attempt whose score is strictly less than this triggers escalation.  A score of
            ``None`` (unknown) never triggers escalation on its own.
        max_duration_ms (int | None): Upper bound on an attempt's wall-clock duration.
            When set, an attempt that takes strictly longer escalates to the next
            provider (the slow result is discarded). ``None`` disables the time gate.
        failure_policy (Literal["raise", "continue"]): What the chain does when it is
            exhausted (no provider accepted).  ``"raise"`` (default) raises
            ``ChainExhaustedError`` — the worker's fail-closed boundary marks the
            document ``failed`` with a precise reason.  ``"continue"`` returns a degraded
            outcome so the stage can run its degraded path and the pipeline proceeds.
        on_degraded (Literal["empty", "best_effort"]): Only consulted when
            ``failure_policy == "continue"``.  ``"empty"`` (default) returns ``result=None``
            (the stage's degraded path runs).  ``"best_effort"`` returns the
            highest-scoring SUCCEEDED attempt's result (even if below ``min_score``) when
            any provider succeeded, falling back to ``empty`` when every provider hard-errored.
    """

    # extra="ignore": old stored gates (and removed knobs like max_cost_usd) must still load.
    model_config = ConfigDict(extra="ignore")

    min_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Escalate when the result's score is strictly below this threshold.",
    )
    max_duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Per-attempt wall-clock budget (ms). An attempt slower than this escalates; None disables.",
    )
    failure_policy: Literal["raise", "continue"] = Field(
        default="raise",
        description=(
            "Exhaustion behaviour: 'raise' aborts the pipeline (doc failed); "
            "'continue' degrades and proceeds."
        ),
    )
    on_degraded: Literal["empty", "best_effort"] = Field(
        default="empty",
        description=(
            "When failure_policy='continue': 'empty' yields result=None (degraded path runs); "
            "'best_effort' returns the highest-scoring succeeded result below threshold."
        ),
    )


__all__ = ["ChainGateConfig"]
