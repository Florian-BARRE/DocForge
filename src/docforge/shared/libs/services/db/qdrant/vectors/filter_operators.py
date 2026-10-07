# ====== Code Summary ======
# FilterOperatorGrammar — the operator form of a search filter value, `{field: {"<op>": value}}`, as
# one pure vocabulary shared by the request gate (422 messages), the stored-value resolver and the
# condition builder. Operators: eq · in · not · not_in · contains · prefix · exists, plus the range
# bounds gte/gt/lte/lt. Which operators a field accepts depends on how Qdrant indexes it (PayloadType).
# An operator object holds ONE operator, or only range bounds (a range is the one unambiguous
# combination). `validate` returns human/agent-readable messages and never raises.

# ====== Standard Library Imports ======
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

# ====== Local Project Imports ======
from .filters import RANGE_KEYS, PayloadType, parse_range


class FilterOp(StrEnum):
    """A non-range filter operator."""

    EQ = "eq"  # equality (same as the bare scalar form)
    IN = "in"  # any-of (same as the bare list form)
    NOT = "not"  # exclusion of one value
    NOT_IN = "not_in"  # exclusion of several values
    CONTAINS = "contains"  # substring (keyword: expanded to stored values; text: full-text match)
    PREFIX = "prefix"  # starts-with (keyword fields only: expanded to stored values)
    EXISTS = "exists"  # field present (true) or absent/null/empty (false)


# Every non-range operator key.
_OP_KEYS = frozenset(op.value for op in FilterOp)
# Operators whose value is a list of scalars.
LIST_OPS = frozenset({FilterOp.IN, FilterOp.NOT_IN})
# Operators that DROP the matching points.
EXCLUSION_OPS = frozenset({FilterOp.NOT, FilterOp.NOT_IN})
# Operators expanded against the stored values on keyword fields.
PATTERN_OPS = frozenset({FilterOp.CONTAINS, FilterOp.PREFIX})
# Max values one list filter may carry (bare list, `in`, `not_in`) — never a fan-out.
MAX_LIST_VALUES = 100

_EQUALITY = (FilterOp.EQ, FilterOp.IN, FilterOp.NOT, FilterOp.NOT_IN)
# Operators (+ whether range bounds are allowed) per payload index type.
_OPS_BY_TYPE: dict[PayloadType, tuple[tuple[FilterOp, ...], bool]] = {
    PayloadType.KEYWORD: ((*_EQUALITY, FilterOp.CONTAINS, FilterOp.PREFIX, FilterOp.EXISTS), False),
    PayloadType.TEXT: ((*_EQUALITY, FilterOp.CONTAINS, FilterOp.EXISTS), False),
    PayloadType.INTEGER: ((*_EQUALITY, FilterOp.EXISTS), True),
    PayloadType.FLOAT: ((FilterOp.EXISTS,), True),
    PayloadType.BOOL: ((FilterOp.EQ, FilterOp.NOT, FilterOp.EXISTS), False),
    PayloadType.DATETIME: ((FilterOp.EXISTS,), True),
}


class FilterOperatorGrammar:
    """Static vocabulary + validation of the `{field: {"<op>": value}}` filter form."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("FilterOperatorGrammar is a static-only class and cannot be instantiated.")

    @staticmethod
    def __shape_error(name: str, op: FilterOp, value: Any) -> str | None:
        """Return why ``value`` is not a valid operand of ``op`` (None when it is)."""
        # 1. exists takes a strict boolean; contains/prefix a non-blank string.
        if op is FilterOp.EXISTS:
            return (
                None if isinstance(value, bool) else f"filter '{name}': 'exists' takes true/false"
            )
        if op in PATTERN_OPS:
            if isinstance(value, str) and value.strip():
                return None
            return f"filter '{name}': '{op}' takes a non-empty string"
        # 2. in/not_in take a bounded, non-empty list of scalars; eq/not a single scalar.
        if op in LIST_OPS:
            if not isinstance(value, list) or not value:
                return f"filter '{name}': '{op}' takes a non-empty list of values"
            if len(value) > MAX_LIST_VALUES:
                return (
                    f"filter '{name}': {len(value)} values exceed the maximum of "
                    f"{MAX_LIST_VALUES} per field"
                )
            items = value
        else:
            items = [value]
        if any(isinstance(item, (list, Mapping)) or item is None for item in items):
            return f"filter '{name}': '{op}' takes scalar value(s) (string, number or boolean)"
        return None

    @staticmethod
    def __range_errors(name: str, spec: Mapping[str, Any], ptype: PayloadType) -> list[str]:
        """Validate a bounds-only operator object against a range-typed field."""
        # 1. Shape (coercible, ordered bounds) first; then the bound kind must match the field.
        try:
            parsed = parse_range(name, spec)
        except ValueError as exc:
            return [str(exc)]
        if parsed.is_datetime != (ptype == PayloadType.DATETIME):
            expected = "ISO-8601 datetime" if ptype == PayloadType.DATETIME else "numeric"
            return [f"field '{name}' expects {expected} range bounds"]
        return []

    @staticmethod
    def allowed(ptype: PayloadType) -> list[str]:
        """
        List the operator keys a field indexed as ``ptype`` accepts.

        Args:
            ptype (PayloadType): The field's Qdrant payload index type.

        Returns:
            list[str]: The operators, then the range bounds when the type is range-typed.
        """
        # 1. The type's operators, then the bounds (range-typed only).
        ops, ranged = _OPS_BY_TYPE[ptype]
        return [op.value for op in ops] + (list(RANGE_KEYS) if ranged else [])

    @staticmethod
    def operator_of(spec: Mapping[str, Any]) -> FilterOp | None:
        """
        Return the single non-range operator of a VALIDATED operator object (None for a range).

        Args:
            spec (Mapping): A gated operator object.

        Returns:
            FilterOp | None: Its operator, or None when it only carries range bounds.
        """
        # 1. A gated object holds either one operator or only bounds.
        return next((FilterOp(key) for key in spec if key in _OP_KEYS), None)

    @classmethod
    def validate(cls, name: str, spec: Mapping[str, Any], ptype: PayloadType | None) -> list[str]:
        """
        Report everything wrong with one field's operator object (empty when it is valid).

        Args:
            name (str): The filtered field.
            spec (Mapping): The operator object as sent.
            ptype (PayloadType | None): The field's payload index type (None = unresolvable).

        Returns:
            list[str]: One message per problem — unknown operator, operator not valid for the
            field type, a forbidden combination, or a malformed operand.
        """
        # 1. An empty object, or keys outside the whole vocabulary, are rejected up front.
        valid = cls.allowed(ptype) if ptype is not None else []
        if not spec:
            return [f"filter '{name}': empty operator object — use one of {valid}"]
        ops = [key for key in spec if key in _OP_KEYS]
        bounds = [key for key in spec if key in RANGE_KEYS]
        unknown = sorted(set(spec) - set(ops) - set(bounds))
        if unknown:
            return [f"filter '{name}': unsupported key(s) {unknown} — valid operators: {valid}"]

        # 2. Only range bounds may combine; one non-range operator stands alone.
        if ops and (bounds or len(ops) > 1):
            return [
                f"filter '{name}': operators {sorted(spec)} cannot be combined — use ONE operator "
                f"per field (only the range bounds {list(RANGE_KEYS)} combine)"
            ]

        # 3. A range needs a range-typed field; an operator must be one the field type accepts.
        label = ptype.value if ptype is not None else "untyped"
        if not ops:
            if ptype is None or not _OPS_BY_TYPE[ptype][1]:
                return [
                    f"field '{name}' is not range-typed ({label}) — a range filter needs an "
                    f"integer, float or datetime field"
                ]
            return cls.__range_errors(name, spec, ptype)
        if ops[0] not in valid:
            return [
                f"filter '{name}': operator '{ops[0]}' is not valid on a {label} field — "
                f"valid: {valid}"
            ]

        # 4. The operand must have the operator's shape, then the field's value type — Qdrant never
        #    coerces, so a mistyped exclusion ({"year": {"not": "2021"}} on an integer field) would
        #    match nothing and therefore exclude NOTHING: the filter would silently widen.
        op = FilterOp(ops[0])
        error = cls.__shape_error(name, op, spec[ops[0]]) or cls.__type_error(
            name, op, spec[ops[0]], ptype
        )
        return [error] if error else []

    @staticmethod
    def __type_error(name: str, op: FilterOp, value: Any, ptype: PayloadType | None) -> str | None:
        """Return why an eq/in/not/not_in operand doesn't match the field's value type (or None)."""
        # 1. Only the value-comparing operators carry typed operands; untyped fields are unchecked.
        if ptype is None or op not in (FilterOp.EQ, FilterOp.IN, FilterOp.NOT, FilterOp.NOT_IN):
            return None
        items = value if isinstance(value, list) else [value]
        # 2. The accepted Python type per index type (bool is an int subclass — excluded explicitly).
        if ptype == PayloadType.INTEGER:
            ok = all(isinstance(item, int) and not isinstance(item, bool) for item in items)
            expected = "integer"
        elif ptype == PayloadType.BOOL:
            ok = all(isinstance(item, bool) for item in items)
            expected = "true/false"
        elif ptype in (PayloadType.KEYWORD, PayloadType.TEXT):
            ok = all(isinstance(item, str) for item in items)
            expected = "string"
        else:
            return None
        if ok:
            return None
        return f"filter '{name}': '{op}' on a {ptype.value} field takes {expected} value(s), got {value!r}"


__all__ = [
    "FilterOp",
    "FilterOperatorGrammar",
    "LIST_OPS",
    "EXCLUSION_OPS",
    "PATTERN_OPS",
    "MAX_LIST_VALUES",
]
