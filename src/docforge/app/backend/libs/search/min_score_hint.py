# ====== Code Summary ======
# MinScoreHint — the honest explanation when a search's min_score threshold removed every hit. Without
# it the empty answer would read as "nothing matched" (or be blamed on a filter), when in fact hits
# existed and only scored below the caller's threshold. Pure: it reads the finalizer's debug note.

# ====== Standard Library Imports ======
from collections.abc import Mapping
from typing import Any

# ====== Local Project Imports ======
from .filter_hint import FilterHint


class MinScoreHint:
    """Static builder of the "min_score cut everything" hint."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MinScoreHint is a static-only class and cannot be instantiated.")

    @staticmethod
    def build(min_score_cut: Mapping[str, Any], hit_count: int) -> list[FilterHint]:
        """
        Return a hint when the min_score threshold dropped every hit, else nothing.

        Args:
            min_score_cut (Mapping[str, Any]): The finalizer's ``debug["min_score"]`` note
                (``threshold``, ``dropped``, ``top_dropped_score``) — empty when no threshold was set.
            hit_count (int): How many hits were delivered after the cut.

        Returns:
            list[FilterHint]: One hint when the threshold emptied the answer, else an empty list.
        """
        # 1. Only an answer the threshold itself emptied deserves this hint.
        dropped = int(min_score_cut.get("dropped") or 0)
        if hit_count > 0 or dropped == 0:
            return []

        # 2. Say how many hits existed and how far the best one was from the threshold.
        threshold = min_score_cut.get("threshold")
        top = min_score_cut.get("top_dropped_score")
        best = f" (best score {top:.4f})" if isinstance(top, int | float) else ""
        message = (
            f"{dropped} hit(s) matched but all scored below min_score={threshold}{best}; "
            f"lower min_score or omit it. Scores depend on score_kind (fusion scores are small)."
        )
        return [FilterHint(field="min_score", value=threshold, message=message)]


__all__ = ["MinScoreHint"]
