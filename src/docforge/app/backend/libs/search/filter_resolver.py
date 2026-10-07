# ====== Code Summary ======
# SearchFilterResolver — the request-edge step that makes metadata filters forgiving and honest before
# the filter map reaches the (pure) search graph. Postgres is the value oracle: each STRING-ish filter
# value (string / enum / keyword_list — bare, or the operand of eq/in/not/not_in) is resolved to the
# exact stored variants matching it ignoring case (one batched query per field), so Qdrant's exact
# `MatchAny` hits "AFD-P0153" for "afd-p0153" and a `not` excludes EVERY case variant. A keyword
# `contains`/`prefix` is expanded to the stored values it covers (→ `{"in": [...]}`); more than
# `MAX_PATTERN_VALUES` is a 422 (never a silent narrowing), none keeps the literal (an honestly empty
# result) plus a hint. A value matching nothing keeps its literal and yields a "did you mean" hint.
# TEXT / TEXT_LIST filters are flagged for full-text matching. Numbers, booleans, datetimes, ranges and
# `exists` pass through untouched. Hints quote the value AS SENT (before enum mapping).

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType
from shared_libs.services.db.facades import MetadataValueResolver
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import (
    EXCLUSION_OPS,
    PATTERN_OPS,
    FilterOp,
    FilterOperatorGrammar,
)

# ====== Local Project Imports ======
from .filter_hint_factory import FilterHintFactory
from .filter_resolution import FilterResolution

# Field types whose filter values are exact keywords — canonicalized case-insensitively.
_KEYWORD_TYPES = frozenset({FieldType.STRING, FieldType.ENUM, FieldType.KEYWORD_LIST})
# Field types with a full-text payload index — filtered by full-text match.
_TEXT_TYPES = frozenset({FieldType.TEXT, FieldType.TEXT_LIST})
# Max distinct stored values one contains/prefix may expand to — past it the caller must narrow.
MAX_PATTERN_VALUES = 500
# A canonicalized eq/not operand that became several variants switches to its list operator.
_LIST_FORM = {FilterOp.EQ: FilterOp.IN, FilterOp.NOT: FilterOp.NOT_IN}


class SearchFilterResolver(LoggerClass):
    """Resolve a search request's filter map against the collection's stored metadata values."""

    def __init__(self, values: MetadataValueResolver) -> None:
        """
        Args:
            values (MetadataValueResolver): The metadata value oracle (``Database.metadata_values``).
        """
        LoggerClass.__init__(self)
        self._values = values
        self._hints = FilterHintFactory(values)

    async def __canonical_value(
        self,
        field: MetadataField,
        value: Any,
        sent: Any,
        resolution: FilterResolution,
        exclusion: bool = False,
    ) -> tuple[Any, bool]:
        """
        Replace a keyword filter value by its stored variants; record a hint for unmatched items.

        Args:
            field (MetadataField): The keyword-typed filtered field.
            value (Any): The gated request value (a scalar or a list).
            sent (Any): The same value as the caller sent it (item-aligned with ``value``: enum
                mapping rewrites items in place, never adds or drops one).
            resolution (FilterResolution): The resolution being built (hints are appended to it).
            exclusion (bool): The value is a ``not``/``not_in`` operand (hint phrasing).

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
                resolution.hints.append(
                    await self._hints.unmatched(field, item, as_sent, exclusion=exclusion)
                )

        # 3. Keep the caller's exact value when nothing changed; a single scalar stays a scalar.
        resolved = list(dict.fromkeys(resolved))
        if resolved == items:
            return value, all_stored
        if not isinstance(value, list) and len(resolved) == 1:
            return resolved[0], all_stored
        return resolved, all_stored

    async def __expand_pattern(
        self,
        field: MetadataField,
        op: FilterOp,
        needle: str,
        sent: Any,
        resolution: FilterResolution,
    ) -> tuple[dict[str, list[str]], bool]:
        """
        Expand a keyword ``contains``/``prefix`` to the stored values it covers.

        Args:
            field (MetadataField): The keyword-typed filtered field.
            op (FilterOp): ``CONTAINS`` or ``PREFIX``.
            needle (str): The pattern.
            sent (Any): The operator object as the caller sent it (quoted by a hint).
            resolution (FilterResolution): The resolution being built (a no-match hint lands here).

        Returns:
            tuple[dict, bool]: ``{"in": stored values}`` (the literal needle when nothing matches —
            an honestly empty result), and whether any stored value matched.

        Raises:
            HTTPException: 422 when the pattern covers more than ``MAX_PATTERN_VALUES`` values — a
                truncated expansion would silently narrow the filter.
        """
        # 1. One bounded read (cap + 1 detects the overflow).
        lookup = self._values.prefix if op is FilterOp.PREFIX else self._values.contains
        stored = await lookup(field, needle, MAX_PATTERN_VALUES + 1)
        if len(stored) > MAX_PATTERN_VALUES:
            raise HTTPException(
                status_code=422,
                detail=(
                    f'Filter \'{field.field_name}\' {{"{op.value}": "{needle}"}} matches more than '
                    f"{MAX_PATTERN_VALUES} distinct stored values — narrow it (a longer "
                    f'{op.value}) or list the values with "in".'
                ),
            )
        # 2. Nothing matched → the literal (no stored value equals it) + an explaining hint.
        if not stored:
            resolution.hints.append(
                await self._hints.no_pattern_match(field, op.value, needle, sent)
            )
            return {FilterOp.IN.value: [needle]}, False
        return {FilterOp.IN.value: stored}, True

    async def __resolve_operator(
        self, field: MetadataField, spec: Mapping[str, Any], sent: Any, resolution: FilterResolution
    ) -> tuple[Any, bool]:
        """
        Resolve a keyword field's operator object (eq/in/not/not_in canonicalized, patterns expanded).

        Returns:
            tuple[Any, bool]: The operator object to run, and whether its values are all stored
            (False for ``exists`` — nothing was verified).
        """
        # 1. exists carries no value to resolve; patterns expand against the stored values.
        op = FilterOperatorGrammar.operator_of(spec)
        if op is None or op is FilterOp.EXISTS:
            return spec, False
        operand = spec[op.value]
        if op in PATTERN_OPS:
            return await self.__expand_pattern(field, op, operand, sent, resolution)

        # 2. eq/in/not/not_in canonicalize their operand; a scalar that became several variants
        #    switches to the list operator (so `not` excludes EVERY stored case variant).
        sent_operand = sent.get(op.value, operand) if isinstance(sent, Mapping) else operand
        canonical, all_stored = await self.__canonical_value(
            field, operand, sent_operand, resolution, exclusion=op in EXCLUSION_OPS
        )
        if isinstance(canonical, list) and op in _LIST_FORM:
            op = _LIST_FORM[op]
        return {op.value: canonical}, all_stored

    async def resolve(
        self,
        filters: dict[str, Any] | None,
        schema: Sequence[MetadataField],
        sent: dict[str, Any] | None = None,
    ) -> FilterResolution:
        """
        Canonicalize string-ish filter values and collect hints for values nothing stores.

        The filter map is assumed already gated (filterable fields, valid operators and ranges,
        enum members) by the route — this step only rewrites values; its one rejection is a
        contains/prefix too broad to expand (422).

        Args:
            filters (dict | None): The gated request filter map (field → scalar, list or operator
                object), enum values already mapped onto their declared members.
            schema (Sequence[MetadataField]): The collection's metadata schema.
            sent (dict | None): The filter map exactly as the caller sent it (before enum mapping);
                hints quote it so a client can find and swap its own value. Defaults to ``filters``.

        Returns:
            FilterResolution: The filter map to run, the full-text fields, the fields whose every
            value was verified as stored, the exclusion fields, and the early hints.

        Raises:
            HTTPException: 422 when a contains/prefix covers more than ``MAX_PATTERN_VALUES`` values.
        """
        # 1. Index the filterable fields; an empty filter map resolves to itself with no I/O.
        gated = dict(filters or {})
        original = dict(sent) if sent is not None else dict(gated)
        by_name = {row.field_name: row for row in schema if row.filterable}
        resolution = FilterResolution(filters=dict(gated), original=original)
        text_fields: set[str] = set()
        verified: set[str] = set()
        exclusions: set[str] = set()

        # 2. Route each filter by its field type: full-text flag, keyword resolution, or as-is.
        for name, value in gated.items():
            field = by_name.get(name)
            field_type = getattr(field, "field_type", None)
            if field is None:
                continue
            if (
                isinstance(value, Mapping)
                and FilterOperatorGrammar.operator_of(value) in EXCLUSION_OPS
            ):
                exclusions.add(name)
            if field_type in _TEXT_TYPES:
                text_fields.add(name)
                continue
            if field_type not in _KEYWORD_TYPES:
                continue
            as_sent = original.get(name, value)
            if isinstance(value, Mapping):
                resolved, all_stored = await self.__resolve_operator(
                    field, value, as_sent, resolution
                )
            else:
                resolved, all_stored = await self.__canonical_value(
                    field, value, as_sent, resolution
                )
            resolution.filters[name] = resolved
            if all_stored:
                verified.add(name)

        resolution.text_fields = frozenset(text_fields)
        resolution.verified_fields = frozenset(verified)
        resolution.exclusion_fields = frozenset(exclusions)
        return resolution


__all__ = ["SearchFilterResolver", "MAX_PATTERN_VALUES"]
