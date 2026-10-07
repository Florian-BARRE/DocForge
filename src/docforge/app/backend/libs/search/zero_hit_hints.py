# ====== Code Summary ======
# ZeroHitHintBuilder — explains a FILTERED search that came back empty with no unmatched keyword value.
# (A value that exists nowhere already carries its own "did you mean" hint from SearchFilterResolver —
# then that filter IS the culprit and nothing more is said; a hint about a not/not_in value explains an
# exclusion that removes nothing, so it never counts as the culprit.) Existence is only claimed when the resolver
# actually verified every value (keyword fields); text/number/bool/range filters are phrased neutrally.
# Pure: it reasons only over the resolution and the hit count, no I/O.

# ====== Standard Library Imports ======
import json
from collections.abc import Mapping
from typing import Any

# ====== Local Project Imports ======
from .filter_hint import FilterHint
from .filter_resolution import FilterResolution


class ZeroHitHintBuilder:
    """Static builder of the "no hits — which filter is the likely culprit" hints."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ZeroHitHintBuilder is a static-only class and cannot be instantiated.")

    @staticmethod
    def build(resolution: FilterResolution, hit_count: int) -> list[FilterHint]:
        """
        Return one hint per filter when a filtered search returned nothing for no obvious reason.

        Args:
            resolution (FilterResolution): The request's resolved filters (and its early hints).
            hit_count (int): How many hits the search delivered.

        Returns:
            list[FilterHint]: Empty when there were hits, no filters, or the early hints already
            name the culprit; else one hint per filter (the single filter is called out as THE
            likely culprit; with several, the combination is).
        """
        # 1. Nothing to explain: hits came back, nothing was filtered, or a culprit is already named
        #    (an exclusion hint is not one — an exclusion that removes nothing cannot empty a result).
        culprits = [h for h in resolution.hints if h.field not in resolution.exclusion_fields]
        if hit_count > 0 or not resolution.original or culprits:
            return []

        # 2. One filter → it is the likely culprit; several → their combination is. "Each value
        #    exists" is only said when the resolver verified every filter's values as stored.
        count = len(resolution.original)
        all_verified = set(resolution.original) <= resolution.verified_fields
        return [
            FilterHint(
                field=name,
                value=value,
                message=ZeroHitHintBuilder.__message(
                    name, value, count, name in resolution.text_fields, all_verified
                ),
            )
            for name, value in resolution.original.items()
        ]

    @staticmethod
    def __message(name: str, value: Any, count: int, full_text: bool, all_verified: bool) -> str:
        """Phrase the zero-hit explanation for one filter."""
        # 1. Render the filter as the caller wrote it (a full-text filter says so; an operator
        #    object renders as its JSON).
        if isinstance(value, Mapping):
            rendered = f"{name} {json.dumps(value, ensure_ascii=False, default=str)}"
        else:
            operator = "matches text" if full_text else "="
            rendered = f"{name} {operator} {json.dumps(value, ensure_ascii=False, default=str)}"

        # 2. A lone filter is the likely culprit; among several, the combination is.
        if count == 1:
            return (
                f"No hit matched the filter {rendered}. It is the only filter, so it is the likely "
                f"culprit — retry without it, or with a broader value."
            )
        if all_verified:
            return (
                f"No hit matched all {count} filters together, including {rendered}. Each value "
                f"exists, so their combination is too narrow — retry dropping one filter at a time."
            )
        return (
            f"No hit matched all {count} filters together, including {rendered}. The combination "
            f"of these filters matches no chunk — retry dropping one filter at a time."
        )


__all__ = ["ZeroHitHintBuilder"]
