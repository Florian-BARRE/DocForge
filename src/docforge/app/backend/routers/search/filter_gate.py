# ====== Code Summary ======
# SearchFilterGate — the request-side filter gate shared by the two filtered reads of a collection
# (POST /search and POST /chunks/browse), so both accept and reject EXACTLY the same filter maps: empty
# or oversized lists, malformed operator objects, non-filterable fields and out-of-enum values are
# rejected 422 before any read, then string-ish values are resolved against the stored values (the
# case-insensitive canonical spelling + "did you mean" hints). One gate, two routes — never forked.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import MetadataField

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.search import (
    EnumFilterCanonicalizer,
    FilterResolution,
    SearchFilterResolver,
    SearchFilterValidator,
)


class SearchFilterGate:
    """Static 422 gate + stored-value resolution of a request's filter map."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchFilterGate is a static-only class and cannot be instantiated.")

    @staticmethod
    async def resolve(
        filters: dict[str, Any] | None,
        schema: Sequence[MetadataField],
    ) -> FilterResolution:
        """
        Gate a request's filter map (422 on any invalid entry) and resolve it to stored values.

        Args:
            filters (dict | None): The filter map exactly as the caller sent it.
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            FilterResolution: The filter map to run, its full-text fields and the early hints.

        Raises:
            HTTPException: 422 naming every invalid filter entry.
        """
        # 1. Empty (Qdrant reads an empty any-of as "no constraint" → a WIDER read) and oversized
        #    list filters are rejected before anything else looks at them.
        list_errors = SearchFilterValidator.list_violations(filters)
        if list_errors:
            raise HTTPException(status_code=422, detail=f"Invalid filter value(s): {list_errors}")

        # 2. Operator objects (ranges included) must be valid for their field's type.
        operator_errors = SearchFilterValidator.operator_violations(filters, schema)
        if operator_errors:
            raise HTTPException(status_code=422, detail=f"Invalid filter(s): {operator_errors}")

        # 3. Only filterable fields may be filtered on.
        _, invalid = SearchFilterValidator.build_conditions(filters, schema)
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Not a filterable field for this collection: {sorted(invalid)}",
            )

        # 4. An ENUM field only accepts its members (case-only differences mapped to the member).
        canonical, enum_errors = EnumFilterCanonicalizer.canonical_enum_filters(filters, schema)
        if enum_errors:
            raise HTTPException(status_code=422, detail=f"Invalid filter value(s): {enum_errors}")

        # 5. Resolve string-ish values against the stored values (Postgres is the value oracle); the
        #    as-sent map rides along so hints quote the caller's own value.
        return await SearchFilterResolver(CONTEXT.database.metadata_values).resolve(
            canonical, schema, sent=filters
        )


__all__ = ["SearchFilterGate"]
