# ====== Code Summary ======
# CorpusMapper — the pure boundary between the grid's (Pydantic) request and the data layer's
# (framework-free) DocumentQuerySpec. It (a) VALIDATES every dynamic reference against the collection
# schema — a metadata filter field must exist and be filterable, its operator must fit the field's
# type, a sort field must be a known base column or an existing metadata field — raising a plain
# ValueError the router turns into a 422 (fail-fast, before any spend), and (b) maps the validated
# request onto the spec, resolving each metadata field name to its concrete id + FieldType. It also
# maps a Document row + its bulk-loaded metadata into a grid row. No DB, no I/O — a static helper.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType
from shared_libs.services.db.postgresql.apis import (
    DocumentQuerySpec,
    MetadataCondition,
    MetadataOp,
    SortDirection,
    SortSpec,
)
from shared_libs.services.db.postgresql.tables import Document, DocumentMetadata, MetadataField

# ====== Local Project Imports ======
from .filters import DocumentFilter, DocumentSort, MetadataFilter
from .models import DocumentGridRow

# The base ``document`` columns the grid may sort by (mirrors DocumentQueryApi's sortable set).
_BASE_SORT_COLUMNS = frozenset(
    {
        "filename",
        "format",
        "status",
        "page_count",
        "file_size",
        "created_at",
        "title",
        "language",
        "enabled",
        "id",
    }
)
# Which operators each field type accepts — a metadata filter outside this set is a clean 422.
_TEXTUAL = {FieldType.STRING, FieldType.TEXT, FieldType.ENUM}
_NUMERIC = {FieldType.INTEGER, FieldType.FLOAT, FieldType.DATETIME}
_LISTS = {
    FieldType.KEYWORD_LIST,
    FieldType.TEXT_LIST,
    FieldType.INTEGER_LIST,
    FieldType.FLOAT_LIST,
}


class CorpusMapper:
    """Static helpers mapping the grid request to the query spec and rows to grid rows."""

    logger = loggerplusplus.bind(identifier="CorpusMapper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CorpusMapper is a static-only class and cannot be instantiated.")

    # -------------------- request -> spec --------------------
    @classmethod
    def to_spec(
        cls,
        filter_: DocumentFilter | None,
        sort: DocumentSort | None,
        schema: Sequence[MetadataField],
    ) -> DocumentQuerySpec:
        """
        Validate the request against the schema and build the fully-resolved query spec.

        Args:
            filter_ (DocumentFilter | None): The per-column filter (None = match everything).
            sort (DocumentSort | None): The sort key (None = default newest-first).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            DocumentQuerySpec: The framework-free spec the data layer executes.

        Raises:
            ValueError: On an unknown/non-filterable field, a bad operator, or an unknown sort field.
        """
        # 1. Index the schema by name once — every reference resolves against it.
        by_name = {field.field_name: field for field in schema}

        # 2. Build the base + metadata predicates, then the id-stabilised sort.
        base = cls._base_kwargs(filter_)
        conditions = cls._metadata_conditions(filter_, by_name)
        sort_spec = cls._sort_spec(sort, by_name)
        return DocumentQuerySpec(metadata=tuple(conditions), sort=sort_spec, **base)

    @staticmethod
    def _base_kwargs(filter_: DocumentFilter | None) -> dict:
        """Translate the typed base-column primitives into the spec's flat keyword fields."""
        if filter_ is None:
            return {}
        kwargs: dict = {}
        # 1. Text columns.
        if filter_.filename is not None:
            kwargs["filename_contains"] = filter_.filename.contains
            kwargs["filename_eq"] = filter_.filename.eq
        if filter_.title is not None:
            kwargs["title_contains"] = filter_.title.contains
        # 2. Enum / set columns (empty list is treated as "no predicate").
        if filter_.status:
            kwargs["statuses"] = tuple(filter_.status)
        if filter_.format:
            kwargs["formats"] = tuple(filter_.format)
        if filter_.language:
            kwargs["languages"] = tuple(filter_.language)
        # 3. Numeric ranges (bytes/pages are integers).
        if filter_.file_size is not None:
            kwargs["file_size_gte"] = _as_int(filter_.file_size.gte)
            kwargs["file_size_lte"] = _as_int(filter_.file_size.lte)
        if filter_.page_count is not None:
            kwargs["page_count_gte"] = _as_int(filter_.page_count.gte)
            kwargs["page_count_lte"] = _as_int(filter_.page_count.lte)
        # 4. Date range + bool.
        if filter_.created_at is not None:
            kwargs["created_after"] = filter_.created_at.gte
            kwargs["created_before"] = filter_.created_at.lte
        if filter_.enabled is not None:
            kwargs["enabled"] = filter_.enabled
        return kwargs

    @classmethod
    def _metadata_conditions(
        cls, filter_: DocumentFilter | None, by_name: dict[str, MetadataField]
    ) -> list[MetadataCondition]:
        """Validate and resolve every metadata filter to a concrete (field_id, type, op) condition."""
        if filter_ is None:
            return []
        conditions: list[MetadataCondition] = []
        for clause in filter_.metadata:
            field = cls._require_filterable(clause, by_name)
            op = cls._require_valid_op(clause, field.field_type)
            cls._require_valid_value(clause, field.field_type, op)
            conditions.append(
                MetadataCondition(
                    field_id=field.id, field_type=field.field_type, op=op, value=clause.value
                )
            )
        return conditions

    @staticmethod
    def _require_filterable(
        clause: MetadataFilter, by_name: dict[str, MetadataField]
    ) -> MetadataField:
        """Resolve a metadata clause's field, requiring it to exist AND be filterable."""
        field = by_name.get(clause.field)
        if field is None:
            raise ValueError(f"Unknown metadata field '{clause.field}'.")
        if not field.filterable:
            raise ValueError(f"Metadata field '{clause.field}' is not filterable.")
        return field

    @staticmethod
    def _require_valid_op(clause: MetadataFilter, field_type: FieldType) -> MetadataOp:
        """Ensure the requested operator fits the field's type, then return it as the enum."""
        op = MetadataOp(clause.op)
        allowed: set[MetadataOp]
        if field_type in _TEXTUAL:
            allowed = {MetadataOp.EQ, MetadataOp.CONTAINS, MetadataOp.IN}
        elif field_type is FieldType.BOOL:
            allowed = {MetadataOp.EQ}
        elif field_type in _NUMERIC:
            allowed = {MetadataOp.EQ, MetadataOp.GTE, MetadataOp.LTE, MetadataOp.IN}
        elif field_type in _LISTS:
            allowed = {MetadataOp.IN, MetadataOp.CONTAINS}
        else:
            allowed = {MetadataOp.EQ}
        if op not in allowed:
            raise ValueError(
                f"Operator '{op}' is invalid for field '{clause.field}' ({field_type})."
            )
        return op

    @staticmethod
    def _require_valid_value(clause: MetadataFilter, field_type: FieldType, op: MetadataOp) -> None:
        """Reject a range bound that cannot be cast to the field's type, as a clean 422.

        Only GTE/LTE cast the bound value server-side (``CAST($1 AS NUMERIC/TIMESTAMP)`` in the data
        layer); a null, boolean, empty or otherwise unparseable bound would otherwise surface as an
        opaque Postgres 500 at query time. EQ/CONTAINS/IN compare as text and never cast the column, so
        they are not validated here. ``clause.value`` is ``Any`` off the wire — coerce-test it, do not
        mutate it (the data layer still binds it as text and lets Postgres parse the cast).
        """
        # 1. Only the typed-cast range operators can crash on a bad bound.
        if op not in (MetadataOp.GTE, MetadataOp.LTE):
            return
        value = clause.value
        # 2. A bool is never a valid numeric/date bound (and bool is an int subclass — screen it first).
        if value is None or isinstance(value, bool):
            raise ValueError(
                f"Filter value for '{clause.field}' ({field_type}) with operator '{op}' "
                f"must be a {field_type} value, got {value!r}."
            )
        # 3. Must parse as the target type — a datetime for DATETIME, a real number otherwise.
        try:
            if field_type is FieldType.DATETIME:
                if isinstance(value, datetime):
                    return
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            else:
                float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Filter value {value!r} for '{clause.field}' ({field_type}) with operator "
                f"'{op}' is not a valid {field_type}."
            )

    @staticmethod
    def _sort_spec(sort: DocumentSort | None, by_name: dict[str, MetadataField]) -> SortSpec:
        """Resolve the sort key to a base column or a metadata field, always id-stabilised."""
        # 1. Default ordering when unspecified.
        if sort is None:
            return SortSpec()
        direction = SortDirection(sort.direction)
        # 2. A base column sorts directly.
        if sort.field in _BASE_SORT_COLUMNS:
            return SortSpec(column=sort.field, direction=direction)
        # 3. Otherwise it must be an existing metadata field (any field — filterable or not).
        field = by_name.get(sort.field)
        if field is None:
            raise ValueError(f"Unknown sort field '{sort.field}'.")
        return SortSpec(
            column=sort.field,
            direction=direction,
            metadata_field_id=field.id,
            metadata_field_type=field.field_type,
        )

    # -------------------- rows --------------------
    @staticmethod
    def grid_row(
        document: Document,
        metadata_rows: Sequence[DocumentMetadata],
        names: dict[int, str],
    ) -> DocumentGridRow:
        """Map a document row + its metadata values into a grid row (a compact name→value map)."""
        # 1. Resolve each metadata value's field name (drop values whose field left the schema).
        values = {names[row.field_id]: row.value for row in metadata_rows if row.field_id in names}
        return DocumentGridRow(
            id=str(document.id),
            filename=document.filename,
            format=document.format,
            status=document.status,
            page_count=document.page_count,
            file_size=document.file_size,
            created_at=document.created_at,
            title=document.title,
            language=document.language,
            enabled=document.enabled,
            metadata=values,
        )


def _as_int(value: float | None) -> int | None:
    """Coerce an optional numeric bound to int for integer columns (bytes/pages)."""
    return None if value is None else int(value)


__all__ = ["CorpusMapper"]
