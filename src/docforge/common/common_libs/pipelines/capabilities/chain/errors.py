# ====== Code Summary ======
# ChainExhaustedError — raised by Chain.call when a chain is exhausted (no provider
# accepted) AND its gate's failure_policy is "raise". Carries the stage label and the
# full per-attempt log so the worker's fail-closed boundary can record a PRECISE reason
# (which providers were tried, their score / error / duration) on the document.

# ====== Local Project Imports ======
from .models import ChainAttempt


class ChainExhaustedError(RuntimeError):
    """
    Raised when a chain exhausts every provider and its policy is ``failure_policy="raise"``.

    The message is built from the per-attempt log so a failed document carries an
    operator-readable cause, e.g.::

        S1 'parse' chain exhausted: all 2 provider(s) failed or scored below threshold:
        docling(score=0.30<0.50, 120ms), mineru(error=TimeoutError: ..., 5000ms)

    Attributes:
        stage (str): Human label of the stage whose chain was exhausted ("parse",
            "ocr", "vlm", "classifier", "embed").
        attempts (list[ChainAttempt]): One record per provider tried, in order.
    """

    def __init__(self, stage: str, attempts: list[ChainAttempt]) -> None:
        """
        Build the precise exhaustion message from the attempt log.

        Args:
            stage (str): Stage label this chain serves.
            attempts (list[ChainAttempt]): Per-provider attempt records.
        """
        # 1. Keep the structured fields for programmatic inspection.
        self.stage = stage
        self.attempts = attempts

        # 2. Render one compact clause per attempt (score-below-threshold OR error).
        clauses = [self._describe(a) for a in attempts]
        detail = ", ".join(clauses) if clauses else "no providers configured"

        # 3. Compose the final operator-readable message.
        super().__init__(
            f"'{stage}' chain exhausted: all {len(attempts)} provider(s) failed or "
            f"scored below threshold: {detail}"
        )

    @staticmethod
    def _describe(attempt: ChainAttempt) -> str:
        """
        Render one attempt as a compact human clause.

        Args:
            attempt (ChainAttempt): The attempt record to describe.

        Returns:
            str: e.g. ``"docling(score=0.30, 120ms)"`` or ``"mineru(error=..., 5000ms)"``.
        """
        # 1. A raised attempt surfaces its error summary.
        if attempt.error is not None:
            return f"{attempt.provider_id}(error={attempt.error}, {attempt.duration_ms}ms)"

        # 2. A scored-but-rejected attempt surfaces its score.
        if attempt.score is not None:
            return f"{attempt.provider_id}(score={attempt.score:.2f}, {attempt.duration_ms}ms)"

        # 3. A succeeded-but-escalated attempt with no score (e.g. tripped the time gate).
        return f"{attempt.provider_id}(rejected, {attempt.duration_ms}ms)"


__all__ = ["ChainExhaustedError"]
