"""CorpusMapper (pure) + DocumentQueryApi (statement assembly): the request→spec mapping resolves
metadata references against the schema (id + type), validates op/type compatibility and sort fields,
shapes a grid row; and the builder compiles an id-stabilised, metadata-EXISTS-carrying statement. No
DB — the mapper is pure and the builder statements are compiled to SQL text only.
"""

import pathlib
import sys
import uuid
from types import SimpleNamespace

import pytest

# The ``backend`` package lives under app/ — put it on the path exactly as the api conftest's
# fastapi_app fixture does, so this pure test module imports it at collection time without booting.
_APP_DIR = str(pathlib.Path(__file__).resolve().parents[3] / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from backend.libs.corpus import (  # noqa: E402
    CorpusMapper,
    DocumentFilter,
    DocumentSort,
    MetadataFilter,
)
from shared_libs.public_models import FieldType  # noqa: E402
from shared_libs.services.db.postgresql.apis import (  # noqa: E402
    DocumentQueryApi,
    MetadataOp,
    SortDirection,
)


def _field(field_id, name, ftype, *, filterable=True):
    return SimpleNamespace(id=field_id, field_name=name, field_type=ftype, filterable=filterable)


# -------------------- request -> spec --------------------
def test_base_filter_maps_to_spec_fields() -> None:
    filter_ = DocumentFilter.model_validate(
        {
            "filename": {"contains": "rep"},
            "status": ["done", "failed"],
            "file_size": {"gte": 100, "lte": 5000},
            "enabled": True,
        }
    )
    spec = CorpusMapper.to_spec(filter_, None, [])
    assert spec.filename_contains == "rep"
    assert spec.statuses == ("done", "failed")
    assert spec.file_size_gte == 100 and spec.file_size_lte == 5000
    assert spec.enabled is True


def test_metadata_condition_is_resolved_to_id_and_type() -> None:
    schema = [_field(7, "year", FieldType.INTEGER)]
    filter_ = DocumentFilter(metadata=[MetadataFilter(field="year", op="gte", value=2020)])
    spec = CorpusMapper.to_spec(filter_, None, schema)
    assert len(spec.metadata) == 1
    cond = spec.metadata[0]
    assert cond.field_id == 7 and cond.field_type == FieldType.INTEGER
    assert cond.op is MetadataOp.GTE and cond.value == 2020


def test_unknown_metadata_field_raises() -> None:
    with pytest.raises(ValueError, match="Unknown metadata field"):
        CorpusMapper.to_spec(
            DocumentFilter(metadata=[MetadataFilter(field="ghost", op="eq", value=1)]), None, []
        )


def test_non_filterable_metadata_field_raises() -> None:
    schema = [_field(1, "notes", FieldType.TEXT, filterable=False)]
    with pytest.raises(ValueError, match="not filterable"):
        CorpusMapper.to_spec(
            DocumentFilter(metadata=[MetadataFilter(field="notes", op="contains", value="x")]),
            None,
            schema,
        )


def test_bad_operator_for_type_raises() -> None:
    schema = [_field(1, "flag", FieldType.BOOL)]
    with pytest.raises(ValueError, match="invalid for field"):
        CorpusMapper.to_spec(
            DocumentFilter(metadata=[MetadataFilter(field="flag", op="contains", value="x")]),
            None,
            schema,
        )


@pytest.mark.parametrize(
    ("ftype", "value"),
    [
        (FieldType.INTEGER, None),  # null bound — previously rendered `>= NULL` (empty), now a 422
        (FieldType.FLOAT, ""),  # empty string — CAST('' AS NUMERIC) would 500 server-side
        (FieldType.INTEGER, True),  # bool is an int subclass but never a valid numeric bound
        (FieldType.INTEGER, "abc"),  # unparseable number
        (FieldType.DATETIME, "not-a-date"),  # unparseable datetime
        (FieldType.DATETIME, None),
    ],
)
def test_range_bound_that_cannot_cast_raises_422(ftype, value) -> None:
    """A GTE/LTE bound that can't cast to the field type is a clean ValueError (422), not a SQL 500."""
    schema = [_field(3, "n", ftype)]
    with pytest.raises(ValueError, match="not a valid|must be a"):
        CorpusMapper.to_spec(
            DocumentFilter(metadata=[MetadataFilter(field="n", op="gte", value=value)]),
            None,
            schema,
        )


@pytest.mark.parametrize(
    ("ftype", "value"),
    [
        (FieldType.INTEGER, 2020),  # native number
        (FieldType.FLOAT, "3.5"),  # numeric string (the wire shape) still accepted
        (FieldType.DATETIME, "2020-01-01T00:00:00Z"),  # ISO string with Z offset
        (FieldType.DATETIME, "2020-01-01"),  # date-only ISO
    ],
)
def test_range_bound_that_casts_is_accepted(ftype, value) -> None:
    """A well-formed numeric/ISO bound (incl. the string wire shape) passes validation unchanged."""
    schema = [_field(3, "n", ftype)]
    spec = CorpusMapper.to_spec(
        DocumentFilter(metadata=[MetadataFilter(field="n", op="lte", value=value)]),
        None,
        schema,
    )
    assert spec.metadata[0].value == value  # value passed through un-mutated (data layer casts it)


def test_sort_base_column_vs_metadata_field() -> None:
    schema = [_field(3, "priority", FieldType.INTEGER)]
    base = CorpusMapper.to_spec(None, DocumentSort(field="filename", direction="asc"), schema)
    assert base.sort.column == "filename"
    assert base.sort.direction is SortDirection.ASC
    assert base.sort.metadata_field_id is None

    meta = CorpusMapper.to_spec(None, DocumentSort(field="priority", direction="desc"), schema)
    assert meta.sort.metadata_field_id == 3
    assert meta.sort.metadata_field_type == FieldType.INTEGER


def test_unknown_sort_field_raises() -> None:
    with pytest.raises(ValueError, match="Unknown sort field"):
        CorpusMapper.to_spec(None, DocumentSort(field="nope"), [])


def test_grid_row_builds_metadata_map_and_drops_unknown_fields() -> None:
    doc = SimpleNamespace(
        id=uuid.uuid4(),
        filename="a.pdf",
        format="pdf",
        status="done",
        page_count=3,
        file_size=10,
        created_at=None,
        title="t",
        language="en",
        enabled=True,
    )
    rows = [
        SimpleNamespace(field_id=1, value="Ada", origin="user"),
        SimpleNamespace(field_id=99, value="orphan", origin="user"),  # field left the schema
    ]
    row = CorpusMapper.grid_row(doc, rows, {1: "author"})
    assert row.metadata == {"author": "Ada"}
    assert row.filename == "a.pdf"


# -------------------- `in` membership per list type (blocker #1 regression) --------------------
def _value_predicate_sql(field_type, value):
    """Compile the `in` value predicate for a single list-typed metadata field to SQL text."""
    schema = [_field(1, "f", field_type)]
    spec = CorpusMapper.to_spec(
        DocumentFilter(metadata=[MetadataFilter(field="f", op="in", value=value)]), None, schema
    )
    return str(DocumentQueryApi._value_predicate(spec.metadata[0]))


def test_string_list_in_uses_has_any_operator() -> None:
    """keyword_list / text_list membership stays a top-level string-key match via ?| (has_any)."""
    assert "?|" in _value_predicate_sql(FieldType.KEYWORD_LIST, ["a", "b"])
    assert "?|" in _value_predicate_sql(FieldType.TEXT_LIST, ["quote"])


def test_number_list_in_uses_jsonb_containment_not_has_any() -> None:
    """integer_list / float_list membership must use @> jsonb_build_array (?| never matches numbers)."""
    for field_type in (FieldType.INTEGER_LIST, FieldType.FLOAT_LIST):
        sql = _value_predicate_sql(field_type, [5, 6])
        assert "@>" in sql and "jsonb_build_array" in sql
        assert "?|" not in sql  # the string-only operator must NOT be used for numbers
        # ANY-membership: one @> per requested value, OR-ed together.
        assert sql.count("@>") == 2 and " OR " in sql


def test_number_list_in_single_value_matches_any_element() -> None:
    """`in [5]` on integer_list compiles to `value @> [5]` — matches a doc whose list is [5,6,7]."""
    sql = _value_predicate_sql(FieldType.INTEGER_LIST, [5])
    # A single-element `in` is a single containment check (the array holds 5 among its elements).
    assert sql.count("@>") == 1 and "jsonb_build_array" in sql


# -------------------- scalar text extraction (P0 jsonb_extract_path_text regression) --------------------
def _scalar_filter_sql(op, value, field_type=FieldType.STRING):
    """Compile a SCALAR-field metadata value predicate (eq/contains/range) to SQL text."""
    schema = [_field(1, "f", field_type)]
    spec = CorpusMapper.to_spec(
        DocumentFilter(metadata=[MetadataFilter(field="f", op=op, value=value)]), None, schema
    )
    return str(DocumentQueryApi._value_predicate(spec.metadata[0]))


def test_scalar_eq_uses_jsonb_arrow_extraction_not_invalid_function() -> None:
    """eq on a scalar field extracts the value via ``#>>`` — the 1-arg jsonb_extract_path_text is
    not a real Postgres function and 500'd at runtime; lock it out of the compiled SQL."""
    sql = _scalar_filter_sql("eq", "Ada")
    assert "#>>" in sql
    assert "jsonb_extract_path_text" not in sql


def test_scalar_contains_and_range_use_arrow_extraction() -> None:
    """contains + ordered comparisons share the same ``#>>`` text extraction (no invalid function)."""
    contains_sql = _scalar_filter_sql("contains", "ad")
    assert "#>>" in contains_sql and "jsonb_extract_path_text" not in contains_sql
    range_sql = _scalar_filter_sql("gte", 2020, field_type=FieldType.INTEGER)
    assert "#>>" in range_sql and "jsonb_extract_path_text" not in range_sql


def test_metadata_sort_subquery_uses_arrow_extraction() -> None:
    """The metadata sort subquery must extract with ``#>>`` too, or its ORDER BY key won't match the
    functional index ``ix_docmeta_field_value_text`` and would reuse the invalid function."""
    schema = [_field(3, "priority", FieldType.INTEGER)]
    spec = CorpusMapper.to_spec(None, DocumentSort(field="priority", direction="desc"), schema)
    statement = DocumentQueryApi._apply_order(DocumentQueryApi._filtered(uuid.uuid4(), spec), spec)
    sql = str(statement)
    assert "#>>" in sql
    assert "jsonb_extract_path_text" not in sql


# -------------------- builder statement assembly --------------------
def test_builder_statement_is_id_stabilised_and_carries_metadata_exists() -> None:
    schema = [_field(4, "author", FieldType.STRING)]
    spec = CorpusMapper.to_spec(
        DocumentFilter(metadata=[MetadataFilter(field="author", op="eq", value="Ada")]),
        DocumentSort(field="created_at", direction="desc"),
        schema,
    )
    statement = DocumentQueryApi._apply_order(DocumentQueryApi._filtered(uuid.uuid4(), spec), spec)
    sql = str(statement)
    # The metadata predicate compiled to a correlated EXISTS over document_metadata, correlated
    # back to the outer document row (not an uncorrelated/broken subquery).
    assert "EXISTS (SELECT 1" in sql
    assert "document_metadata.document_id = document.id" in sql
    # The ordering is stabilised by document.id ASC as the FINAL tie-breaking key (after the
    # requested created_at DESC), not merely present somewhere unrelated in the statement.
    assert "ORDER BY document.created_at DESC" in sql
    assert sql.rstrip().endswith("document.id ASC")
