# ====== Code Summary ======
# ExampleRequestBuilder — builds 2–4 ready-to-send search request bodies from a collection's REAL
# described fields and stored example values: a plain content search, an equality filter on a real
# value, a `search_in` on a vector-indexed metadata field, then a range (numeric/datetime) or an any-of
# filter. Values are coerced to their field's JSON type so the body works verbatim. Pure — no I/O.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from .field_guide_builder import VALUE_MAX_CHARS
from .models import FieldGuide

# The query text of the examples — a placeholder the client replaces with its question.
EXAMPLE_QUERY = "your question here"
EXAMPLE_LIMIT = 5
MAX_EXAMPLES = 4

# Types an equality example may use (exact match is meaningful + the value round-trips as JSON).
_EQUALITY_TYPES = frozenset(
    {FieldType.STRING, FieldType.ENUM, FieldType.KEYWORD_LIST, FieldType.BOOL, FieldType.INTEGER}
)
# Types an any-of example may use.
_ANY_OF_TYPES = frozenset({FieldType.STRING, FieldType.ENUM, FieldType.KEYWORD_LIST})
# Types the search route accepts a range on.
_RANGE_TYPES = frozenset({FieldType.INTEGER, FieldType.FLOAT, FieldType.DATETIME})


class ExampleRequestBuilder:
    """Pure builder of example search bodies from a collection's described fields."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a namespace of pure helpers."""
        raise TypeError(f"{cls.__name__} is a static namespace and cannot be instantiated.")

    @classmethod
    def build(cls, fields: Sequence[FieldGuide]) -> list[dict[str, Any]]:
        """
        Build up to MAX_EXAMPLES search bodies using the collection's real fields and values.

        Args:
            fields (Sequence[FieldGuide]): The collection's described fields (with example values).

        Returns:
            list[dict[str, Any]]: Search request bodies — always at least the plain content search.
        """
        # 1. The plain content search is always valid.
        examples: list[dict[str, Any]] = [{"query": EXAMPLE_QUERY, "limit": EXAMPLE_LIMIT}]

        # 2. Each candidate builder contributes one body when the schema/values allow it.
        for make in (cls.__equality, cls.__search_in, cls.__range, cls.__any_of):
            body = make(fields)
            if body is not None:
                examples.append(body)
        return examples[:MAX_EXAMPLES]

    @classmethod
    def __equality(cls, fields: Sequence[FieldGuide]) -> dict[str, Any] | None:
        """A content search filtered on a real value of a filterable keyword-like field."""
        # 1. First filterable field of an equality type with a usable value.
        found = cls.__first_value(fields, _EQUALITY_TYPES, minimum=1)
        if found is None:
            return None
        field, values = found
        return {
            "query": EXAMPLE_QUERY,
            "limit": EXAMPLE_LIMIT,
            "filters": {field.name: cls.__coerce(field.type, values[0])},
        }

    @staticmethod
    def __search_in(fields: Sequence[FieldGuide]) -> dict[str, Any] | None:
        """A search over content AND a vector-indexed metadata field (prefers a semantic one)."""
        # 1. Prefer a semantic field, else a lexical-only one.
        indexed = [field for field in fields if field.semantic or field.lexical]
        if not indexed:
            return None
        field = next((f for f in indexed if f.semantic), indexed[0])
        return {
            "query": EXAMPLE_QUERY,
            "limit": EXAMPLE_LIMIT,
            "search_in": [
                {"field": "content", "semantic": True, "lexical": True},
                {"field": field.name, "semantic": field.semantic, "lexical": field.lexical},
            ],
        }

    @classmethod
    def __range(cls, fields: Sequence[FieldGuide]) -> dict[str, Any] | None:
        """A content search with a lower-bound range on a real numeric/datetime value."""
        # 1. First filterable range-typed field with a usable value.
        found = cls.__first_value(fields, _RANGE_TYPES, minimum=1)
        if found is None:
            return None
        field, values = found
        bound = cls.__coerce(field.type, values[0])
        return {
            "query": EXAMPLE_QUERY,
            "limit": EXAMPLE_LIMIT,
            "filters": {field.name: {"gte": bound}},
        }

    @classmethod
    def __any_of(cls, fields: Sequence[FieldGuide]) -> dict[str, Any] | None:
        """A content search matching any of two real values of a filterable keyword field."""
        # 1. First filterable keyword field with at least two usable values.
        found = cls.__first_value(fields, _ANY_OF_TYPES, minimum=2)
        if found is None:
            return None
        field, values = found
        return {
            "query": EXAMPLE_QUERY,
            "limit": EXAMPLE_LIMIT,
            "filters": {field.name: values[:2]},
        }

    @staticmethod
    def __first_value(
        fields: Sequence[FieldGuide], types: frozenset[FieldType], minimum: int
    ) -> tuple[FieldGuide, list[str]] | None:
        """
        Find the first filterable field of ``types`` carrying at least ``minimum`` usable values.

        A truncated sample value would never match the stored one, so only values shorter than the
        truncation cap are usable in a filter.

        Returns:
            tuple[FieldGuide, list[str]] | None: The field and its usable values, or None.
        """
        # 1. Scan in schema order; the first fitting field wins.
        for field in fields:
            if not field.filterable or field.type not in types:
                continue
            values = [value for value in field.example_values if len(value) < VALUE_MAX_CHARS]
            if len(values) >= minimum:
                return field, values
        return None

    @staticmethod
    def __coerce(field_type: FieldType, value: str) -> Any:
        """
        Coerce a stored text value to its field's JSON type (strings stay strings).

        Returns:
            Any: An int / float / bool for those types, else the string unchanged.
        """
        # 1. Numbers and booleans are stored as their text form; the filter wants the JSON type.
        try:
            if field_type == FieldType.INTEGER:
                return int(value)
            if field_type == FieldType.FLOAT:
                return float(value)
        except ValueError:
            return value
        if field_type == FieldType.BOOL:
            return value.lower() == "true"
        return value


__all__ = ["ExampleRequestBuilder"]
