# ====== Code Summary ======
# ReingestEstimateGate — makes a LARGE bulk reingest an acknowledged decision. Above
# CORPUS_REINGEST_CONFIRM_THRESHOLD matched documents the caller must pass ``confirm_estimate=true``;
# otherwise the call is refused 409 ``estimate_required`` carrying the cost/volume estimate summary so
# the caller sees what they are about to spend (hosted providers, shared embedder load) first. A
# ``replay_from`` reingest is priced on the replayed stages only (the estimator prices the whole rail;
# the gate keeps the stage lines at/after the replay start — parse-time OCR is never re-spent).
# The bulk routes need only WRITE while the estimate endpoint needs READ_TECHNICAL, so the refusal body
# carries counts + cost totals only; the technical detail (priced stages, token totals, caveats naming
# models/providers/rate keys) is added solely for a caller holding READ_TECHNICAL.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.estimate import CostEstimate
from shared_libs.pipelines.ingest.replay import STAGE_RANK
from shared_libs.pipelines.ingest.stages import StageKey

# ====== Local Project Imports ======
from ..estimate import CollectionEstimateRequest, CostEstimateService


class ReingestEstimateGate(LoggerClass):
    """Requires an explicit acknowledgement before a bulk reingest above a size threshold."""

    # The summary keys any WRITE caller may see (no model/provider/rate detail).
    _PUBLIC_KEYS: tuple[str, ...] = (
        "document_count",
        "total_cost_usd",
        "total_cost_lower_bound_usd",
        "cost_complete",
    )

    def __init__(self, estimator: CostEstimateService, threshold: int) -> None:
        """
        Args:
            estimator (CostEstimateService): Produces the pre-hoc estimate shown in the refusal.
            threshold (int): CORPUS_REINGEST_CONFIRM_THRESHOLD. <= 0 disables the gate.
        """
        LoggerClass.__init__(self)
        self._estimator = estimator
        self._threshold = threshold

    async def require(
        self,
        collection_id: uuid.UUID,
        matched: int,
        confirm_estimate: bool,
        estimate_request: CollectionEstimateRequest,
        replay_from: str | None = None,
        technical: bool = False,
    ) -> None:
        """
        Pass when the reingest is small or acknowledged; otherwise raise 409 with the estimate.

        Args:
            collection_id (uuid.UUID): The collection being reingested.
            matched (int): The resolved target count (BEFORE the fan-out cap — the user is confirming
                the whole intent, not just the first page of it).
            confirm_estimate (bool): The request's acknowledgement flag.
            estimate_request (CollectionEstimateRequest): The SAME selection (ids / filter / scope=all)
                the reingest targets, so the estimate covers exactly those documents.
            replay_from (str | None): The (already validated) replay start stage; when set only the
                stages at/after it are priced.
            technical (bool): The caller holds READ_TECHNICAL — include the technical detail.

        Raises:
            HTTPException: 409 ``estimate_required`` (with ``estimate``) when ``matched`` exceeds the
                threshold and ``confirm_estimate`` is false.
        """
        # 1. Disabled, small, or acknowledged → pass.
        if self._threshold <= 0 or matched <= self._threshold or confirm_estimate:
            return
        # 2. Compute the summary (best-effort: a failing estimator must not mask the refusal).
        summary: dict | None = None
        try:
            estimate = await self._estimator.estimate(collection_id, estimate_request)
            if estimate is not None:
                summary = self.summarize(estimate, replay_from, technical=technical)
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"Estimate for the reingest gate failed ({error!r})")
        # 3. Refuse with the actionable detail.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "estimate_required",
                "message": (
                    f"This reingest targets {matched} documents (> {self._threshold}). Review the "
                    f"estimate and resend with confirm_estimate=true to proceed."
                ),
                "matched": matched,
                "threshold": self._threshold,
                "estimate": summary,
            },
        )

    @classmethod
    def summarize(
        cls, estimate: CostEstimate, replay_from: str | None, *, technical: bool = False
    ) -> dict:
        """
        Fold an estimate into the refusal summary, keeping only the replayed stages on a replay.

        Args:
            estimate (CostEstimate): The full-rail estimate over the targeted documents.
            replay_from (str | None): The replay start stage, or None for a full reingest.
            technical (bool): Include the technical detail (READ_TECHNICAL callers only).

        Returns:
            dict: document_count, cost totals and completeness; with ``technical`` also the token
                totals, the priced stage names and the estimator caveats (plus a replay caveat).
        """
        full = cls.__full_summary(estimate, replay_from)
        if technical:
            return full
        return {key: full[key] for key in cls._PUBLIC_KEYS}

    @staticmethod
    def __full_summary(estimate: CostEstimate, replay_from: str | None) -> dict:
        """The complete (technical) summary — totals, priced stages and caveats."""
        # 1. Full reingest → the estimator's own totals.
        if replay_from is None:
            return {
                "document_count": estimate.document_count,
                "total_cost_usd": estimate.total_cost_usd,
                "total_cost_lower_bound_usd": estimate.total_cost_lower_bound_usd,
                "cost_complete": estimate.cost_complete,
                "total_prompt_tokens": estimate.total_prompt_tokens,
                "total_completion_tokens": estimate.total_completion_tokens,
                "priced_stages": [stage.stage for stage in estimate.stages],
                "caveats": estimate.caveats,
            }
        # 2. Replay → re-total over the stage lines at/after the start (parse-time "ocr" is upstream).
        start = STAGE_RANK[StageKey(replay_from)]
        kept = [s for s in estimate.stages if ReingestEstimateGate.__rank(s.stage) >= start]
        known = [s.cost_usd for s in kept if s.cost_usd is not None]
        complete = len(known) == len(kept)
        return {
            "document_count": estimate.document_count,
            "total_cost_usd": sum(known) if complete else None,
            "total_cost_lower_bound_usd": sum(known),
            "cost_complete": complete,
            "total_prompt_tokens": sum(s.prompt_tokens for s in kept),
            "total_completion_tokens": sum(s.completion_tokens for s in kept),
            "priced_stages": [s.stage for s in kept],
            "caveats": [
                *estimate.caveats,
                f"replay_from={replay_from}: only the stages from {replay_from} onward are priced.",
            ],
        }

    @staticmethod
    def __rank(estimate_stage: str) -> int:
        """Rail rank of an estimator stage line (enrich_ocr/enrich_vlm → enrich; unknown → upstream)."""
        # 1. The enrich sub-lines are not StageKey values themselves.
        if estimate_stage.startswith("enrich_"):
            return STAGE_RANK[StageKey.ENRICH]
        # 2. An unrecognised line is treated as pre-IR (never priced on a replay).
        try:
            return STAGE_RANK[StageKey(estimate_stage)]
        except (ValueError, KeyError):
            return STAGE_RANK[StageKey.PARSE]


__all__ = ["ReingestEstimateGate"]
