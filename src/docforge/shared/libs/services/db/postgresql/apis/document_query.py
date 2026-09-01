# ====== Code Summary ======
# DocumentQueryApi — the index-friendly, N+1-free engine behind the large-scale document grid. It
# turns a fully-resolved DocumentQuerySpec into ONE SQLAlchemy statement per need: a filtered+sorted
# page of rows, the total matching count, and the bare id set a bulk selector resolves to. Base
# columns filter on ``document`` directly; dynamic metadata filters become correlated EXISTS
# subqueries on ``document_metadata`` (keyed by the pre-resolved field_id), so the plan stays a set
# of index seeks rather than a fan-out join. Every ordering is stabilised by ``document.id`` so
# offset paging never skips or duplicates a row. Session-driven, Postgres-only, spends nothing.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import (
    TIMESTAMP,
    Numeric,
    Select,
    String,
    cast,
    func,
    literal,
    literal_column,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..tables import Document, DocumentMetadata
from .document_query_spec import DocumentQuerySpec, MetadataCondition, MetadataOp, SortDirection

# Base columns the grid may sort by — the map guards against an arbitrary attribute reaching getattr.
_SORTABLE_COLUMNS: dict[str, Any] = {
    "filename": Document.filename,
    "format": Document.format,
    "status": Document.status,
    "page_count": Document.page_count,
    "file_size": Document.file_size,
    "created_at": Document.created_at,
    "title": Document.title,
    "language": Document.language,
    "enabled": Document.enabled,
    "id": Document.id,
}
# Field types whose JSONB value is compared as a number / timestamp rather than as text.
_NUMERIC_TYPES = {FieldType.INTEGER, FieldType.FLOAT}
# List-typed fields split by element kind: `?|` (has_any) only matches STRING array elements, so
# number arrays must use JSONB `@>` containment instead (a `?|` on numbers silently never matches).
_STRING_LIST_TYPES = {FieldType.KEYWORD_LIST, FieldType.TEXT_LIST}
_NUMBER_LIST_TYPES = {FieldType.INTEGER_LIST, FieldType.FLOAT_LIST}


class DocumentQueryApi:
    """Static data-access API: filtered/sorted/paginated document reads + the selector id set."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentQueryApi is a static-only class and cannot be instantiated.")

    # -------------------- public reads --------------------
    @classmethod
    async def query(
        cls,
        session: AsyncSession,
        collection_id: uuid.UUID,
        spec: DocumentQuerySpec,
        limit: int,
        offset: int,
    ) -> list[Document]:
        """Return one filtered, sorted, id-stabilised page of a collection's documents."""
        # 1. Filter, then order, then window — the ordering carries id as its secondary key.
        statement = cls._apply_order(cls._filtered(collection_id, spec), spec)
        result = await session.execute(statement.limit(limit).offset(offset))
        return list(result.scalars().all())

    @classmethod
    async def count(
        cls, session: AsyncSession, collection_id: uuid.UUID, spec: DocumentQuerySpec
    ) -> int:
        """Return how many documents match the filter (the grid's total, for the pager)."""
        # 1. COUNT over the same predicates — no ordering, no window.
        statement = (
            select(func.count()).select_from(Document).where(*cls._conditions(collection_id, spec))
        )
        return int((await session.execute(statement)).scalar_one())

    @classmethod
    async def resolve_ids(
        cls, session: AsyncSession, collection_id: uuid.UUID, spec: DocumentQuerySpec
    ) -> list[uuid.UUID]:
        """Return every matching document id — the concrete target set a filter-selector expands to."""
        # 1. Bare id projection over the same predicates (no ordering needed for a set).
        statement = select(Document.id).where(*cls._conditions(collection_id, spec))
        return list((await session.execute(statement)).scalars().all())

    # -------------------- statement assembly --------------------
    @classmethod
    def _filtered(cls, collection_id: uuid.UUID, spec: DocumentQuerySpec) -> Select:
        """The document SELECT with every filter predicate applied (no ordering/window yet)."""
        return select(Document).where(*cls._conditions(collection_id, spec))

    @classmethod
    def _conditions(
        cls, collection_id: uuid.UUID, spec: DocumentQuerySpec
    ) -> list[ColumnElement[bool]]:
        """Build every WHERE predicate: the collection scope, base columns, then metadata EXISTS."""
        conditions: list[ColumnElement[bool]] = [Document.collection_id == collection_id]
        cls._append_base(conditions, spec)
        for condition in spec.metadata:
            conditions.append(cls._metadata_exists(condition))
        return conditions

    @staticmethod
    def _append_base(conditions: list[ColumnElement[bool]], spec: DocumentQuerySpec) -> None:
        """Append the base-column predicates present in the spec (each is optional)."""
        # 1. String columns — contains is case-insensitive (LIKE metachars escaped), eq is exact.
        if spec.filename_contains is not None:
            conditions.append(_ilike_contains(Document.filename, spec.filename_contains))
        if spec.filename_eq is not None:
            conditions.append(Document.filename == spec.filename_eq)
        if spec.title_contains is not None:
            conditions.append(_ilike_contains(Document.title, spec.title_contains))
        # 2. Enum / set columns — membership.
        if spec.statuses:
            conditions.append(Document.status.in_(spec.statuses))
        if spec.formats:
            conditions.append(Document.format.in_(spec.formats))
        if spec.languages:
            conditions.append(Document.language.in_(spec.languages))
        # 3. Numeric ranges.
        if spec.file_size_gte is not None:
            conditions.append(Document.file_size >= spec.file_size_gte)
        if spec.file_size_lte is not None:
            conditions.append(Document.file_size <= spec.file_size_lte)
        if spec.page_count_gte is not None:
            conditions.append(Document.page_count >= spec.page_count_gte)
        if spec.page_count_lte is not None:
            conditions.append(Document.page_count <= spec.page_count_lte)
        # 4. Date range.
        if spec.created_after is not None:
            conditions.append(Document.created_at >= spec.created_after)
        if spec.created_before is not None:
            conditions.append(Document.created_at <= spec.created_before)
        # 5. Bool.
        if spec.enabled is not None:
            conditions.append(Document.enabled.is_(spec.enabled))

    @classmethod
    def _metadata_exists(cls, condition: MetadataCondition) -> ColumnElement[bool]:
        """Turn one metadata predicate into a correlated EXISTS on ``document_metadata``."""
        # 1. Correlate the value row to the outer document + its (pre-resolved) field id.
        predicate = cls._value_predicate(condition)
        return (
            select(1)
            .where(
                DocumentMetadata.document_id == Document.id,
                DocumentMetadata.field_id == condition.field_id,
                predicate,
            )
            .exists()
        )

    @classmethod
    def _value_predicate(cls, condition: MetadataCondition) -> ColumnElement[bool]:
        """The JSONB value comparison for one metadata condition, typed by the field's kind."""
        column = DocumentMetadata.value
        text = _as_text(column)
        # 1. Substring — text over the JSON scalar's text form (LIKE metacharacters escaped).
        if condition.op is MetadataOp.CONTAINS:
            return _ilike_contains(text, condition.value)
        # 2. Membership — any list element (list field) or the scalar itself in the given set.
        if condition.op is MetadataOp.IN:
            return cls._in_predicate(column, text, condition)
        # 3. Ordered comparisons — cast BOTH the JSON text AND the bound value to number/timestamp.
        #    The request value arrives as a plain str/int/float (Pydantic's MetadataFilter.value:
        #    Any never coerces a datetime string to a real datetime), so leaving the bound value
        #    untyped makes SQLAlchemy infer VARCHAR for it — and Postgres has no `timestamp >=
        #    varchar` operator (unlike numeric-vs-float, which Postgres compares via implicit casts,
        #    so this only ever surfaced for DATETIME fields).
        if condition.op in (MetadataOp.GTE, MetadataOp.LTE):
            typed = cls._typed_value(text, condition.field_type)
            bound = cls._typed_bound(condition.value, condition.field_type)
            if condition.op is MetadataOp.GTE:
                return typed >= bound
            return typed <= bound
        # 4. Equality — compare the JSON scalar's text form to the stringified value.
        return text == str(condition.value)

    @staticmethod
    def _in_predicate(column: Any, text: Any, condition: MetadataCondition) -> ColumnElement[bool]:
        """
        ANY-membership for the ``in`` operator, correct for BOTH scalar and list-typed fields.

        - Scalar field (string/enum/int/float…): the stored value's text form is one of the wanted.
        - STRING-array field (keyword_list/text_list): Postgres ``?|`` (``has_any``) over the array's
          string elements — a top-level string key match.
        - NUMBER-array field (integer_list/float_list): ``?|`` only matches STRING keys, so it would
          silently never match JSON numbers. Use JSONB containment instead: the row matches when the
          stored array CONTAINS any one requested number, i.e. ``value @> '[n]'`` OR-ed per value
          (each ``@> '[n]'`` is "the array contains n"). Backed by the GIN index on ``value``.
        """
        wanted = (
            condition.value if isinstance(condition.value, (list, tuple)) else [condition.value]
        )
        # 1. String-array fields — top-level string-key membership via ?|.
        if condition.field_type in _STRING_LIST_TYPES:
            return column.has_any(array([str(item) for item in wanted]))
        # 2. Number-array fields — ANY-containment: OR of per-value @> '[n]' (numbers, not strings).
        if condition.field_type in _NUMBER_LIST_TYPES:
            return or_(*(column.contains(func.jsonb_build_array(item)) for item in wanted))
        # 3. Scalar fields — the value's text form is one of the requested set.
        return text.in_([str(item) for item in wanted])

    @staticmethod
    def _typed_value(text: Any, field_type: FieldType) -> Any:
        """Cast the JSONB text column to Numeric/Timestamp for an ordered comparison."""
        # 1. Number vs timestamp vs raw text — driven by the resolved field type.
        if field_type in _NUMERIC_TYPES:
            return cast(text, Numeric)
        if field_type is FieldType.DATETIME:
            return cast(text, TIMESTAMP)
        return text

    @staticmethod
    def _typed_bound(value: Any, field_type: FieldType) -> Any:
        """
        Cast a GTE/LTE request value to the SAME SQL type as ``_typed_value``'s column side.

        The value is stringified and bound as ``String`` FIRST, then SQL-``CAST`` to Numeric/
        Timestamp — never bound directly with ``type_=Numeric``/``TIMESTAMP``: asyncpg's
        type-directed parameter encoder demands a native ``Decimal``/``datetime`` for those DBAPI
        types and raises before the query ever reaches Postgres, whereas a plain text bind lets
        Postgres itself parse the cast server-side (matching how the column side is already text).
        """
        bound = literal(str(value), type_=String)
        if field_type in _NUMERIC_TYPES:
            return cast(bound, Numeric)
        if field_type is FieldType.DATETIME:
            return cast(bound, TIMESTAMP)
        return bound

    @classmethod
    def _apply_order(cls, statement: Select, spec: DocumentQuerySpec) -> Select:
        """Append the requested ordering, always stabilised by ``document.id`` as the last key."""
        sort = spec.sort
        descending = sort.direction is SortDirection.DESC
        # 1. A metadata sort orders by a correlated scalar value subquery; a base sort by the column.
        if sort.metadata_field_id is not None:
            key: Any = cls._metadata_sort_key(sort.metadata_field_id, sort.metadata_field_type)
        else:
            key = _SORTABLE_COLUMNS.get(sort.column, Document.created_at)
        ordered = key.desc() if descending else key.asc()
        # 2. NULLS LAST keeps unset values out of the way; id is the deterministic tie-break.
        return statement.order_by(ordered.nulls_last(), Document.id.asc())

    @staticmethod
    def _metadata_sort_key(field_id: int, field_type: FieldType | None) -> Any:
        """A correlated scalar subquery yielding one document's value for the sorted field."""
        base = (
            select(_as_text(DocumentMetadata.value))
            .where(
                DocumentMetadata.document_id == Document.id,
                DocumentMetadata.field_id == field_id,
            )
            .correlate(Document)
            .scalar_subquery()
        )
        if field_type in _NUMERIC_TYPES:
            return cast(base, Numeric)
        if field_type is FieldType.DATETIME:
            return cast(base, TIMESTAMP)
        return base


def _as_text(column: Any) -> Any:
    """The JSONB scalar's UNQUOTED text form (a string stays 'Ada', not '"Ada"') for compare/cast."""
    # ``#>>`` with an empty path array yields the whole scalar as unquoted text. Rendered inline as
    # ``value #>> '{}'`` (via literal_column, NOT a bound param) so it matches the functional index
    # ``ix_docmeta_field_value_text`` expression byte-for-byte — a placeholder would defeat the index.
    # (The 1-arg ``jsonb_extract_path_text(value)`` this replaced is not a real Postgres function.)
    return column.op("#>>")(literal_column("'{}'"))


def _escape_like(value: str) -> str:
    """Escape LIKE/ILIKE metacharacters so a user-supplied ``%``/``_`` matches literally."""
    # Backslash first (it is the escape char), then the two wildcards.
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ilike_contains(column: Any, value: str) -> ColumnElement[bool]:
    """A case-insensitive substring predicate with metacharacters escaped and an explicit ESCAPE."""
    # The literal is escaped so ``50%`` matches the text "50%" rather than "50<anything>".
    return column.ilike(f"%{_escape_like(value)}%", escape="\\")


__all__ = ["DocumentQueryApi"]
