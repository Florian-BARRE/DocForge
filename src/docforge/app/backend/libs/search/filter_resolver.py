# ====== Code Summary ======
# SearchFilterResolver — the request-edge step that makes metadata filters forgiving and honest before
# the filter map reaches the (pure) search graph. Postgres is the value oracle: each STRING-ish filter
# value (string / enum / keyword_list) is resolved to the exact stored variants matching it ignoring
# case (one batched query per field), so Qdrant's exact `MatchAny` then hits "AFD-P0153" for
# "afd-p0153". A value matching nothing keeps its literal (the result is honestly empty) and yields a
# hint with the closest stored values (suggestions are computed for the first few unmatched values only
# — a bounded fan-out). TEXT / TEXT_LIST filters are flagged for full-text matching. Numbers, booleans,
# datetimes and ranges pass through untouched. Hints quote the value AS SENT (before enum mapping).

# ====== Standard Library Imports ======
import json
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope, FieldType
from shared_libs.services.db.facades import MetadataValueResolver
from shared_libs.services.db.postgresql.tables import MetadataField

# ====== Local Project Imports ======
from .filter_hint import FilterHint
from .filter_resolution import FilterResolution

# Field types whose filter values are exact keywords — canonicalized case-insensitively.
_KEYWORD_TYPES = frozenset({FieldType.STRING, FieldType.ENUM, FieldType.KEYWORD_LIST})
# Field types with a full-text payload index — filtered by full-text match.
_TEXT_TYPES = frozenset({FieldType.TEXT, FieldType.TEXT_LIST})
# How many "closest stored values" a hint offers.
_SUGGESTION_COUNT = 5
# How many unmatched values per request get "closest stored values" (each costs a bounded pool read +
# difflib); the rest are still hinted, without suggestions.
_SUGGESTED_VALUE_BUDGET = 5


class SearchFilterResolver(LoggerClass):
    """Resolve a search request's filter map against the collection's stored metadata values."""

    def __init__(self, values: MetadataValueResolver) -> None:
        """
        Args:
            values (MetadataValueResolver): The metadata value oracle (``Database.metadata_values``).
        """
        LoggerClass.__init__(self)
        self._values = values
        self._suggestion_budget = _SUGGESTED_VALUE_BUDGET

    async def resolve(
        self,
        filters: dict[str, Any] | None,
        schema: Sequence[MetadataField],
        sent: dict[str, Any] | None = None,
    ) -> FilterResolution:
        """
        Canonicalize string-ish filter values and collect hints for values nothing stores.

        The filter map is assumed already gated (filterable fields, valid ranges, enum members) by
        the route — this step only rewrites values, never rejects.

        Args:
            filters (dict | None): The gated request filter map (field → scalar, list or range),
                enum values already mapped onto their declared members.
            schema (Sequence[MetadataField]): The collection's metadata schema.
            sent (dict | None): The filter map exactly as the caller sent it (before enum mapping);
                hints quote it so a client can find and swap its own value. Defaults to ``filters``.

        Returns:
            FilterResolution: The filter map to run, the full-text fields, the fields whose every
            value was verified as stored, and the early hints.
        """
        # 1. Index the filterable fields; an empty filter map resolves to itself with no I/O.
        gated = dict(filters or {})
        original = dict(sent) if sent is not None else dict(gated)
        by_name = {row.field_name: row for row in schema if row.filterable}
        resolution = FilterResolution(filters=dict(gated), original=original)
        self._suggestion_budget = _SUGGESTED_VALUE_BUDGET
        text_fields: set[str] = set()
        verified: set[str] = set()

        # 2. Route each filter by its field type: full-text flag, keyword canonicalization, or as-is.
        for name, value in gated.items():
            field = by_name.get(name)
            field_type = getattr(field, "field_type", None)
            if field is None or isinstance(value, Mapping):
                continue
            if field_type in _TEXT_TYPES:
                text_fields.add(name)
            elif field_type in _KEYWORD_TYPES:
                canonical, all_stored = await self.__canonical_value(
                    field, value, original.get(name, value), resolution
                )
                resolution.filters[name] = canonical
                if all_stored:
                    verified.add(name)

        resolution.text_fields = frozenset(text_fields)
        resolution.verified_fields = frozenset(verified)
        return resolution

    async def __canonical_value(
        self, field: MetadataField, value: Any, sent: Any, resolution: FilterResolution
    ) -> tuple[Any, bool]:
        """
        Replace a keyword filter value by its stored variants; record a hint for unmatched items.

        Args:
            field (MetadataField): The keyword-typed filtered field.
            value (Any): The gated request value (a scalar or a list — any-of).
            sent (Any): The same filter's value as the caller sent it (item-aligned with ``value``:
                enum mapping rewrites items in place, never adds or drops one).
            resolution (FilterResolution): The resolution being built (hints are appended to it).

        Returns:
            tuple[Any, bool]: The original value when it already IS exactly what is stored
            (byte-identical filter for exact-case callers), else the scalar/list of canonical
            variants (+ unmatched literals); and whether EVERY item was found stored.
        """
        # 1. One batched lookup for every string item of the value (non-strings stay literal).
        items = value if isinstance(value, list) else [value]
        sent_items = sent if isinstance(sent, list) else [sent]
        if len(sent_items) != len(items):
            sent_items = items
        strings = [item for item in items if isinstance(item, str)]
        canonical = await self._values.canonicalize(field, strings) if strings else {}

        # 2. Expand each item into its stored variants; an unmatched item keeps its literal + a hint.
        resolved: list[Any] = []
        all_stored = True
        for item, as_sent in zip(items, sent_items, strict=True):
            variants = canonical.get(item) if isinstance(item, str) else None
            if variants:
                resolved.extend(variants)
                continue
            all_stored = False
            resolved.append(item)
            if isinstance(item, str):
                resolution.hints.append(await self.__unmatched_hint(field, item, as_sent))

        # 3. Keep the caller's exact value when nothing changed; a single scalar stays a scalar.
        resolved = list(dict.fromkeys(resolved))
        if resolved == items:
            return value, all_stored
        if not isinstance(value, list) and len(resolved) == 1:
            return resolved[0], all_stored
        return resolved, all_stored

    async def __unmatched_hint(self, field: MetadataField, item: str, as_sent: Any) -> FilterHint:
        """
        Build the "did you mean" hint for a filter value no stored value matches, even ignoring case.

        Only the first ``_SUGGESTED_VALUE_BUDGET`` unmatched values of a request are ranked against
        the stored values; later ones are hinted without suggestions (bounded fan-out).

        Args:
            field (MetadataField): The filtered field.
            item (str): The unmatched (gated) value — what was looked up.
            as_sent (Any): The same value as the caller sent it — what the hint quotes.

        Returns:
            FilterHint: The hint naming the value and offering the closest stored values.
        """
        # 1. Rank the closest stored values (bounded queries) while the request's budget lasts.
        holder = "chunk" if getattr(field, "scope", None) == FieldScope.CHUNK else "document"
        rendered = json.dumps(as_sent, ensure_ascii=False, default=str)
        if self._suggestion_budget <= 0:
            return FilterHint(
                field=field.field_name,
                value=as_sent,
                message=f"No {holder} has {field.field_name} = {rendered}.",
            )
        self._suggestion_budget -= 1
        suggestions = await self._values.suggest(field, item, k=_SUGGESTION_COUNT)

        # 2. Phrase it for a human or an agent: what failed, and what to try instead.
        tail = (
            f"Closest stored values: {', '.join(suggestions)}."
            if suggestions
            else "No stored value of this field is close to it."
        )
        self.logger.debug(f"Filter value {rendered} matches no stored '{field.field_name}' value")
        return FilterHint(
            field=field.field_name,
            value=as_sent,
            message=f"No {holder} has {field.field_name} = {rendered}. {tail}",
            suggestions=suggestions,
        )


__all__ = ["SearchFilterResolver"]
