# ====== Code Summary ======
# EnumFilterCanonicalizer — maps ENUM filter values (bare, or eq/in/not/not_in operands) onto their
# declared members ignoring case, and reports values outside the enum for a 422. Pure, store-free.

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import PATTERN_OPS, FilterOp, FilterOperatorGrammar


class EnumFilterCanonicalizer:
    """Static case-insensitive canonicalization of enum filter values."""

    logger = loggerplusplus.bind(identifier="EnumFilterCanonicalizer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "EnumFilterCanonicalizer is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def __enum_members(name: str, value: Any, allowed: list[Any], errors: list[str]) -> Any:
        """
        Map an enum filter operand (scalar or list) onto its declared members, ignoring case.

        Args:
            name (str): The enum field.
            value (Any): The operand (a scalar, or a list for any-of / not_in).
            allowed (list): The field's declared members.
            errors (list[str]): Collects one message per value outside the enum (mutated).

        Returns:
            Any: The operand with each item replaced by its member (unknown items kept as sent).
        """
        # 1. Exact member first, then a case-insensitive match; an unknown item is reported.
        by_lower = {str(member).lower(): member for member in allowed}
        items = value if isinstance(value, list) else [value]
        canonical: list[Any] = []
        for item in items:
            member = item if item in allowed else by_lower.get(str(item).lower())
            if member is None:
                errors.append(
                    f"field '{name}' value {item!r} is not an allowed value — allowed values: "
                    f"{', '.join(str(member) for member in allowed)}"
                )
            canonical.append(member if member is not None else item)
        return canonical if isinstance(value, list) else canonical[0]

    @staticmethod
    def canonical_enum_filters(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """
        Map ENUM filter values onto their declared members, ignoring case; report unknown values.

        A field declared with ``enum_values`` accepts only those members (the same rule upload-time
        admission enforces). A value differing from a member only by case is rewritten to that
        member (``"POLICY"`` → ``"policy"``); a value matching no member otherwise returns 200 with 0
        hits — a typo'd filter reads as "nothing matches" — so it is reported for a 422 naming the
        field and its allowed values. Non-enum and non-filterable fields pass through untouched
        (filterability is gated separately).

        Args:
            filters (dict | None): The requested constraints (field → scalar or list).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            tuple[dict | None, list[str]]: The filter map with enum values canonicalized (None when
            the request had none), and one message per value outside its enum (empty when valid).
        """
        # 1. Index the filterable enum fields → their allowed members (skip fields without one).
        enums = {
            row.field_name: list(getattr(row, "enum_values", None) or [])
            for row in schema
            if row.filterable and getattr(row, "enum_values", None)
        }
        if filters is None:
            return None, []

        # 2. Rewrite every enum value (a list filter is any-of) to its member, or report it. An
        #    operator object maps its eq/in/not/not_in operand the same way; contains/prefix/exists
        #    operands are patterns or flags, not members (resolved against stored values later).
        mapped: dict[str, Any] = dict(filters)
        errors: list[str] = []
        for name, value in filters.items():
            allowed = enums.get(name)
            if allowed is None:
                continue
            if not isinstance(value, Mapping):
                mapped[name] = EnumFilterCanonicalizer.__enum_members(name, value, allowed, errors)
                continue
            op = FilterOperatorGrammar.operator_of(value)
            if op is None or op in PATTERN_OPS or op is FilterOp.EXISTS:
                continue
            operand = value[op.value]
            mapped[name] = {
                op.value: EnumFilterCanonicalizer.__enum_members(name, operand, allowed, errors)
            }
        return mapped, errors


__all__ = ["EnumFilterCanonicalizer"]
