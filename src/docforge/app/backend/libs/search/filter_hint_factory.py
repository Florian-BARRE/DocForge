# ====== Code Summary ======
# FilterHintFactory — phrases the early "this filter cannot match what you think" hints of ONE search
# request, with the closest stored values as suggestions: a value no stored value equals (even ignoring
# case), an exclusion value nothing stores (the exclusion removes nothing), and a contains/prefix
# pattern no stored value matches. Suggestions cost a bounded read each, so only the first few hints
# of a request get them (a per-request budget); later ones are still hinted, without suggestions.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope
from shared_libs.services.db.facades import MetadataValueResolver
from shared_libs.services.db.postgresql.tables import MetadataField

# ====== Local Project Imports ======
from .filter_hint import FilterHint

# How many stored values a hint offers.
_SUGGESTION_COUNT = 5
# How many hints per request get suggestions (each costs a bounded pool read + difflib).
_SUGGESTED_HINT_BUDGET = 5


class FilterHintFactory(LoggerClass):
    """Build one request's filter hints, spending a bounded suggestion budget."""

    def __init__(self, values: MetadataValueResolver) -> None:
        """
        Args:
            values (MetadataValueResolver): The metadata value oracle (suggestion source).
        """
        LoggerClass.__init__(self)
        self._values = values
        self._budget = _SUGGESTED_HINT_BUDGET

    @staticmethod
    def __holder(field: MetadataField) -> str:
        """Name what carries the field's value — a chunk or a document."""
        # 1. Chunk-scope values live per chunk; everything else per document.
        return "chunk" if getattr(field, "scope", None) == FieldScope.CHUNK else "document"

    async def __suggestions(self, field: MetadataField, needle: str, examples: bool) -> list[str]:
        """
        Spend one budget unit on the closest stored values (empty once the budget is spent).

        Args:
            field (MetadataField): The filtered field.
            needle (str): The value to rank stored values against.
            examples (bool): Fall back to the most frequent stored values when nothing is close.

        Returns:
            list[str]: Up to ``_SUGGESTION_COUNT`` stored values.
        """
        # 1. Budget spent → no more reads this request.
        if self._budget <= 0:
            return []
        self._budget -= 1
        # 2. Closest first; a pattern with nothing close still shows what IS stored.
        ranked = await self._values.suggest(field, needle, k=_SUGGESTION_COUNT)
        if not ranked and examples:
            ranked = await self._values.distinct_values(field, limit=_SUGGESTION_COUNT)
        return ranked

    async def unmatched(
        self, field: MetadataField, item: str, as_sent: Any, exclusion: bool = False
    ) -> FilterHint:
        """
        Hint a filter value no stored value matches, even ignoring case.

        Args:
            field (MetadataField): The filtered field.
            item (str): The unmatched (gated) value — what was looked up.
            as_sent (Any): The same value as the caller sent it — what the hint quotes.
            exclusion (bool): The value came from ``not``/``not_in`` (it excludes nothing).

        Returns:
            FilterHint: The hint naming the value and offering the closest stored values.
        """
        # 1. Rank the closest stored values while the request's budget lasts.
        rendered = json.dumps(as_sent, ensure_ascii=False, default=str)
        head = f"No {self.__holder(field)} has {field.field_name} = {rendered}"
        head += ", so this exclusion removes nothing." if exclusion else "."
        has_budget = self._budget > 0
        suggestions = await self.__suggestions(field, item, examples=False)
        self.logger.debug(f"Filter value {rendered} matches no stored '{field.field_name}' value")

        # 2. Phrase it for a human or an agent: what failed, and what to try instead.
        if not has_budget:
            return FilterHint(field=field.field_name, value=as_sent, message=head)
        tail = (
            f"Closest stored values: {', '.join(suggestions)}."
            if suggestions
            else "No stored value of this field is close to it."
        )
        return FilterHint(
            field=field.field_name,
            value=as_sent,
            message=f"{head} {tail}",
            suggestions=suggestions,
        )

    async def no_pattern_match(
        self, field: MetadataField, operator: str, needle: str, as_sent: Any
    ) -> FilterHint:
        """
        Hint a ``contains``/``prefix`` pattern no stored value matches (the result is empty).

        Args:
            field (MetadataField): The filtered field.
            operator (str): ``"contains"`` or ``"prefix"``.
            needle (str): The pattern.
            as_sent (Any): The whole operator object as the caller sent it.

        Returns:
            FilterHint: The hint naming the pattern and offering stored values to retry with.
        """
        # 1. Closest stored values, else the most frequent ones (budget permitting).
        verb = "contains" if operator == "contains" else "starts with"
        suggestions = await self.__suggestions(field, needle, examples=True)
        rendered = json.dumps(needle, ensure_ascii=False)
        message = (
            f"No stored value of {field.field_name} {verb} {rendered} (case-insensitive), so this "
            f"filter matches nothing."
        )
        if suggestions:
            message += f" Examples of stored values: {', '.join(suggestions)}."
        return FilterHint(
            field=field.field_name, value=as_sent, message=message, suggestions=suggestions
        )


__all__ = ["FilterHintFactory"]
