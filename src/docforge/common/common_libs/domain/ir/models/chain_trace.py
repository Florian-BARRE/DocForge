# ====== Code Summary ======
# Chain provenance models: ChainAttemptIR and ChainTrace.
# These two models are tightly related — ChainTrace aggregates ChainAttemptIR records —
# so they share a file per the tightly-related exception.
# Filled by providers.chain.Chain.call and stamped on the IR for audit purposes.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ChainAttemptIR(BaseModel):
    """
    Serialisable record of one provider attempt within a stage's chain.

    Mirrors ``providers.chain.ChainAttempt`` so the IR can be persisted as jsonb
    and round-tripped through Postgres without the dataclass dependency.  The
    stage code converts each ``ChainAttempt`` into a ``ChainAttemptIR`` at the
    boundary so the IR layer stays free of provider imports.

    Attributes:
        provider_id (str): Stable identifier of the provider (e.g. ``"docling"``).
        score (float | None): Self-reported quality in ``[0.0, 1.0]`` or None.
        duration_ms (int): Wall-clock duration of this attempt.
        succeeded (bool): False when the call raised or returned None.
        escalated (bool): True when the gate told the chain to try the next provider.
        error (str | None): Exception summary captured when the attempt raised.
    """

    provider_id: str
    score: float | None = None
    duration_ms: int
    succeeded: bool
    escalated: bool
    error: str | None = None


class ChainTrace(BaseModel):
    """
    Full audit trail of one chain invocation, stamped on the IR.

    Stage-level traces (``parse``, ``embed``) live on the ``DocumentIR``; block-level
    traces (``classifier``, ``ocr``, ``vlm``) live on the individual ``Block`` so each
    figure carries its own lineage.

    Attributes:
        stage (str): Stage label (``"parse"``, ``"ocr"``, ``"vlm"``,
            ``"classifier"``, ``"embed"``).
        attempts (list[ChainAttemptIR]): One record per provider tried, in order.
        final_provider (str | None): provider_id of the attempt whose result was
            kept, or None when every provider escalated.
        degraded (bool): True when the chain exhausted under ``failure_policy="continue"``
            and the stage ran its degraded path (no provider accepted). The UI surfaces
            this so a degraded stage is a first-class signal rather than silent loss.
            Default False keeps legacy IR rows loading unchanged.
        gate_tripped (str | None): Which gate caused the final escalation when degraded —
            ``"score"`` (below min_score), ``"time"`` (over max_duration_ms), or ``"error"``
            (the last provider raised). None when not degraded or undeterminable.
    """

    stage: str
    attempts: list[ChainAttemptIR] = Field(default_factory=list)
    final_provider: str | None = None
    degraded: bool = False
    gate_tripped: str | None = None
