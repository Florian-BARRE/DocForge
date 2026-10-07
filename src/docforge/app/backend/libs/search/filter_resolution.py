# ====== Code Summary ======
# FilterResolution — the outcome of resolving a request's filter map against the collection's stored
# metadata values (SearchFilterResolver): the filter map to hand the search graph (string-ish values
# replaced by their exact stored variants), the fields whose filters must run as full-text matches,
# the hints already known before the search runs, and the caller's original map (for zero-hit hints).

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Local Project Imports ======
from .filter_hint import FilterHint


@dataclass(slots=True)
class FilterResolution:
    """
    A request filter map resolved against Postgres (the value oracle).

    Attributes:
        filters (dict[str, Any]): The filter map to run — string-ish values canonicalized to the
            exact stored variants; every other value untouched.
        original (dict[str, Any]): The caller's filter map, as sent.
        text_fields (frozenset[str]): Filtered fields with a full-text payload index (text/text_list).
        verified_fields (frozenset[str]): Keyword-typed filtered fields whose EVERY value was found
            stored (case-insensitively) — the only fields a zero-hit hint may claim "exist".
        hints (list[FilterHint]): Hints for filter values that match no stored value at all.
    """

    filters: dict[str, Any] = field(default_factory=dict)
    original: dict[str, Any] = field(default_factory=dict)
    text_fields: frozenset[str] = frozenset()
    verified_fields: frozenset[str] = frozenset()
    hints: list[FilterHint] = field(default_factory=list)


__all__ = ["FilterResolution"]
