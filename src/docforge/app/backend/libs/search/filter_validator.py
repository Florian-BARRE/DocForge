# ====== Code Summary ======
# SearchFilterValidator — the pure 422 gates over a search filter map: filterability (and the typed
# Qdrant Conditions over the accepted fields), list size, and operator objects ({field: {"<op>": v}})
# checked against each field's payload type via the shared FilterOperatorGrammar. Never raises.

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import DatabaseHelpers
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import (
    MAX_LIST_VALUES,
    Condition,
    FilterOperatorGrammar,
    PayloadType,
    build_match_conditions,
)


class SearchFilterValidator:
    """Static, store-free validation of a search request's filter map."""

    logger = loggerplusplus.bind(identifier="SearchFilterValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchFilterValidator is a static-only class and cannot be instantiated.")

    # Max values one list filter may carry (any-of): a larger list is a caller error, never a fan-out.
    MAX_FILTER_LIST_VALUES = MAX_LIST_VALUES

    @staticmethod
    def _payload_type(field: MetadataField | None) -> PayloadType | None:
        """
        Resolve a field's Qdrant payload index type, defensively — None when unresolvable.

        Only an operator object needs a field's type, so this is looked up lazily (never for a
        plain scalar/list filter). A field object that carries no ``field_type`` (a lightweight
        stand-in shape) or an unmapped type yields None rather than raising — the grammar then
        reports a clean 422 instead of a 500.
        """
        # 1. A missing field (unknown/non-filterable) or a shape without a declared type → None.
        field_type = getattr(field, "field_type", None)
        if field_type is None:
            return None
        # 2. Map the declared type to its payload index type; an unmapped type is treated as None.
        try:
            return DatabaseHelpers.payload_type_for(field_type)
        except KeyError:
            return None

    @staticmethod
    def build_conditions(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> tuple[list[Condition], list[str]]:
        """
        Translate a {field: value} filter map into typed Conditions over the FILTERABLE fields.

        Args:
            filters (dict | None): The requested constraints (field → scalar or list).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            tuple[list[Condition], list[str]]: The ANDed conditions, and the names of any
            requested fields that are unknown or not filterable (the route rejects these 422).
        """
        # 1. Only the fields flagged filterable are indexed for payload filtering in Qdrant;
        #    a non-filterable field is reported so the route can 422, never silently matched.
        filterable = {row.field_name for row in schema if row.filterable}
        accepted: dict[str, Any] = {}
        invalid: list[str] = []
        for name, value in (filters or {}).items():
            if name in filterable:
                accepted[name] = value
            else:
                invalid.append(name)
        # 2. Build the conditions over the accepted subset with the shared mapping (list → any-of,
        #    scalar → exact) — order preserved, so the built filter is byte-identical.
        return build_match_conditions(accepted), invalid

    @staticmethod
    def list_violations(filters: dict[str, Any] | None) -> list[str]:
        """
        Report list filters that are empty or longer than ``MAX_FILTER_LIST_VALUES``.

        An empty any-of list would reach Qdrant as an empty ``should`` — which Qdrant treats as "no
        constraint", silently WIDENING the search instead of matching nothing. An oversized list
        would fan out one stored-value lookup per item. Both are rejected 422 for every field type.

        Args:
            filters (dict | None): The requested constraints (field → scalar, list, or range map).

        Returns:
            list[str]: One human-readable message per offending filter (empty when all valid).
        """
        # 1. Only list values are checked; scalars and range mappings are other gates' concern.
        errors: list[str] = []
        for name, value in (filters or {}).items():
            if not isinstance(value, list):
                continue
            if not value:
                errors.append(
                    f"filter '{name}': an empty list matches nothing — omit the filter or give at "
                    f"least one value"
                )
            elif len(value) > SearchFilterValidator.MAX_FILTER_LIST_VALUES:
                errors.append(
                    f"filter '{name}': {len(value)} values exceed the maximum of "
                    f"{SearchFilterValidator.MAX_FILTER_LIST_VALUES} per field"
                )
        return errors

    @staticmethod
    def operator_violations(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> list[str]:
        """
        Report operator-object filters (``{field: {"<op>": value}}``) a field cannot accept.

        Every operator object is validated against the field's payload index type by the shared
        ``FilterOperatorGrammar``: an unknown operator, an operator the type does not support (e.g.
        ``prefix`` on an integer), a forbidden combination (only range bounds combine), a malformed
        operand, or a range whose bound kind does not match the field (a datetime field needs
        ISO-8601 bounds, a numeric field numeric bounds). Non-filterable fields are the
        filterability gate's concern, not this check's.

        This runs on EVERY search, so it must never raise: a plain scalar/list filter is skipped
        untouched (its field type is never inspected).

        Args:
            filters (dict | None): The requested constraints (field → scalar, list, or operator
                object).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            list[str]: One human-readable message per problem (empty when all valid).
        """
        # 1. Index the FILTERABLE fields by name — typed lazily, only when an operator needs it.
        by_name = {row.field_name: row for row in schema if getattr(row, "filterable", False)}
        errors: list[str] = []
        for name, value in (filters or {}).items():
            # 2. Only an operator object is checked here; an unknown field is another gate's.
            if not isinstance(value, Mapping) or name not in by_name:
                continue
            ptype = SearchFilterValidator._payload_type(by_name[name])
            errors.extend(FilterOperatorGrammar.validate(name, value, ptype))
        return errors


__all__ = ["SearchFilterValidator"]
