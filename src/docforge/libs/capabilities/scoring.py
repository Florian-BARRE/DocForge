# ====== Code Summary ======
# ScoredResult — the single Protocol every chain-able result type implements.
#
# A result that wants to participate in chain escalation exposes a ``score()`` method
# returning a value in ``[0.0, 1.0]`` (higher = better) or ``None`` when the score is
# unknown.  The chain's gate (see ``providers/chain_gate.py``) interprets ``None`` as
# "good enough" — escalation is only triggered by an explicit low score.
#
# This decouples scoring from the chain itself: providers own the meaning of "quality"
# for their own output (Docling's textual-block ratio, OCR's avg per-character
# confidence, the VLM heuristic of structured-output validity, …), the chain simply
# threads the value through to the gate.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ScoredResult(Protocol):
    """
    A provider result that can self-rate for chain escalation.

    The ``score()`` return value is interpreted as follows by the gate:
      • ``[0.0, 1.0]`` — quality estimate; lower than ``min_score`` ⇒ escalate.
      • ``None`` — score unknown; the gate treats it as "good enough" and does not
        escalate on score grounds alone (other gate criteria still apply).
    """

    def score(self) -> float | None:
        """Return a quality estimate in ``[0.0, 1.0]`` or ``None`` when unknown."""
        ...
