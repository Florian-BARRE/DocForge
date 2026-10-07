# ====== Code Summary ======
# FilterHint — one actionable explanation attached to a search response when a filter cannot be the
# reason for good results: a filter value that matches no stored value (even ignoring case), or a
# filtered search that returned nothing. Carried as a 200 payload (never an error status) so a caller
# — human or LLM agent — learns WHICH filter to change and to WHAT, instead of a bare empty result.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FilterHint:
    """
    A "did you mean" / "likely culprit" explanation about one search filter.

    Attributes:
        field (str): The filtered metadata field the hint is about.
        value (Any): The filter value as the caller sent it (one list item, or the whole value).
        message (str): The English, human/agent-readable explanation.
        suggestions (list[str]): Closest stored values to retry with (may be empty).
    """

    field: str
    value: Any
    message: str
    suggestions: list[str] = field(default_factory=list)


__all__ = ["FilterHint"]
