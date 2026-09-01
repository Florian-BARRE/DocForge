"""EXECUTES the corpus query builder (DocumentQueryApi) against a real Postgres — the
``jsonb_extract_path_text(1-arg)`` bug shipped because every prior test only asserted the SQLAlchemy
statement's SHAPE (see tests/units/api/test_corpus_query_route.py), never ran it. Postgres rejected
that 1-arg call as "function does not exist" only once a real query executed.

Covers, end to end: every ``MetadataOp`` (EQ/CONTAINS/IN/GTE/LTE), scalar vs JSONB metadata fields,
sort asc/desc on a base column AND a metadata field (numeric-cast, not lexicographic), pagination
(limit/offset), and the numeric-list IN path — the ``?|`` (has_any, string keys only) vs ``@>``
(containment, numbers) distinction from a prior fix: a ``?|`` on a number array silently matches
nothing, so ``ratings in [7]`` only proving right if it hits the ``@>`` branch.

One seeded collection, shared read-only across the whole module (nothing here mutates a row after
setup), each test opening its own engine/session against the session-scoped migrated throwaway db.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared_libs.public_models import FieldOrigin
from shared_libs.public_models.contract import FieldType
from shared_libs.services.db.postgresql.apis.document_query import DocumentQueryApi
from shared_libs.services.db.postgresql.apis.document_query_spec import (
    DocumentQuerySpec,
    MetadataCondition,
    MetadataOp,
    SortDirection,
    SortSpec,
)
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentMetadata,
    DocumentStatus,
    MetadataField,
    SourceKind,
)

pytestmark = pytest.mark.db

_BASE_TIME = datetime(2024, 1, 1, tzinfo=UTC)

# One row per seeded document: (label, filename, format, status, page_count, file_size, language,
# enabled, author, year, rank, score, tags, ratings, published_at).
_DOCS = [
    dict(
        label="D1",
        filename="alpha.pdf",
        format="pdf",
        status=DocumentStatus.DONE,
        page_count=10,
        file_size=1000,
        language="en",
        enabled=True,
        author="Ada Lovelace",
        year=2020,
        rank=9,
        score=3.5,
        tags=["ml", "nlp"],
        ratings=[1, 2, 3],
        published_at="2020-06-15T00:00:00",
    ),
    dict(
        label="D2",
        filename="beta.pdf",
        format="pdf",
        status=DocumentStatus.DONE,
        page_count=20,
        file_size=2000,
        language="en",
        enabled=True,
        author="Bob Smith",
        year=2021,
        rank=10,
        score=4.2,
        tags=["nlp"],
        ratings=[4, 5],
        published_at="2021-06-15T00:00:00",
    ),
    dict(
        label="D3",
        filename="gamma.docx",
        format="docx",
        status=DocumentStatus.PENDING,
        page_count=5,
        file_size=500,
        language="fr",
        enabled=False,
        author="Ada Lovelace",
        year=2019,
        rank=2,
        score=2.1,
        tags=["vision"],
        ratings=[9],
        published_at="2019-06-15T00:00:00",
    ),
    dict(
        label="D4",
        filename="delta.pdf",
        format="pdf",
        status=DocumentStatus.FAILED,
        page_count=30,
        file_size=3000,
        language="en",
        enabled=True,
        author="Chloe Zhang",
        year=2022,
        rank=100,
        score=4.9,
        tags=["ml", "vision"],
        ratings=[7, 8],
        published_at="2022-06-15T00:00:00",
    ),
    dict(
        label="D5",
        filename="epsilon.pdf",
        format="pdf",
        status=DocumentStatus.DONE,
        page_count=15,
        file_size=1500,
        language="en",
        enabled=True,
        author="Ada Lovelace",
        year=2023,
        rank=3,
        score=3.9,
        tags=[],
        ratings=[],
        published_at="2023-06-15T00:00:00",
    ),
]


@pytest.fixture(scope="module")
async def seeded(migrated_db_dsn: str) -> AsyncIterator[dict]:
    """Seed one collection + 5 documents (scalar + JSONB metadata) once for the whole module."""
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as session:
            collection = Collection(
                name=f"corpus-query-exec-{uuid.uuid4().hex[:8]}",
                supported_formats=["pdf", "docx"],
                max_file_size_bytes=10_000_000,
            )
            session.add(collection)
            await session.flush()
            collection_id = collection.id

            fields = {
                "author": MetadataField(
                    collection_id=collection.id,
                    field_name="author",
                    field_type=FieldType.STRING,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
                "year": MetadataField(
                    collection_id=collection.id,
                    field_name="year",
                    field_type=FieldType.INTEGER,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
                "rank": MetadataField(
                    collection_id=collection.id,
                    field_name="rank",
                    field_type=FieldType.INTEGER,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
                "score": MetadataField(
                    collection_id=collection.id,
                    field_name="score",
                    field_type=FieldType.FLOAT,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
                "tags": MetadataField(
                    collection_id=collection.id,
                    field_name="tags",
                    field_type=FieldType.KEYWORD_LIST,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
                "ratings": MetadataField(
                    collection_id=collection.id,
                    field_name="ratings",
                    field_type=FieldType.INTEGER_LIST,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
                "published_at": MetadataField(
                    collection_id=collection.id,
                    field_name="published_at",
                    field_type=FieldType.DATETIME,
                    filterable=True,
                    origin=FieldOrigin.USER,
                ),
            }
            session.add_all(fields.values())
            await session.flush()
            field_ids = {name: field.id for name, field in fields.items()}

            doc_ids: dict[str, uuid.UUID] = {}
            for i, spec in enumerate(_DOCS):
                document = Document(
                    collection_id=collection.id,
                    source_hash=f"hash-{spec['label']}",
                    filename=spec["filename"],
                    format=spec["format"],
                    mime_type="application/octet-stream",
                    file_size=spec["file_size"],
                    page_count=spec["page_count"],
                    language=spec["language"],
                    source_kind=SourceKind.DIGITAL_BORN,
                    title=f"Title {spec['label']}",
                    status=spec["status"],
                    pipeline_version="v1",
                    enabled=spec["enabled"],
                    created_at=_BASE_TIME + timedelta(days=i),
                    updated_at=_BASE_TIME + timedelta(days=i),
                )
                session.add(document)
                await session.flush()
                doc_ids[spec["label"]] = document.id

                for field_name, value in (
                    ("author", spec["author"]),
                    ("year", spec["year"]),
                    ("rank", spec["rank"]),
                    ("score", spec["score"]),
                    ("tags", spec["tags"]),
                    ("ratings", spec["ratings"]),
                    ("published_at", spec["published_at"]),
                ):
                    session.add(
                        DocumentMetadata(
                            document_id=document.id,
                            field_id=field_ids[field_name],
                            value=value,
                            origin=FieldOrigin.USER,
                        )
                    )
            await session.commit()

        yield {"collection_id": collection_id, "field_ids": field_ids, "doc_ids": doc_ids}
    finally:
        await engine.dispose()


@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine + session per test — read-only against the already-seeded module data."""
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            yield db_session
    finally:
        await engine.dispose()


def _spec(**kwargs) -> DocumentQuerySpec:
    return DocumentQuerySpec(**kwargs)


async def _labels(session: AsyncSession, seeded: dict, spec: DocumentQuerySpec) -> list[str]:
    """The seeded LABELS (not raw UUIDs) matching the spec, in the order ``query`` returns them."""
    rows = await DocumentQueryApi.query(session, seeded["collection_id"], spec, limit=100, offset=0)
    by_id = {doc_id: label for label, doc_id in seeded["doc_ids"].items()}
    return [by_id[row.id] for row in rows]


# -------------------- base-column filters (execution, not just shape) --------------------


async def test_filename_contains_executes_ilike(session, seeded) -> None:
    spec = _spec(
        filename_contains="ta", sort=SortSpec(column="filename", direction=SortDirection.ASC)
    )
    assert await _labels(session, seeded, spec) == ["D2", "D4"]  # beta.pdf, delta.pdf


async def test_status_membership(session, seeded) -> None:
    spec = _spec(
        statuses=(DocumentStatus.DONE,),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, spec) == ["D1", "D2", "D5"]


async def test_enabled_bool_and_resolve_ids(session, seeded) -> None:
    spec = _spec(enabled=True)
    ids = await DocumentQueryApi.resolve_ids(session, seeded["collection_id"], spec)
    expected = {seeded["doc_ids"][label] for label in ("D1", "D2", "D4", "D5")}
    assert set(ids) == expected


# -------------------- metadata operators (execution) --------------------


async def test_metadata_eq_scalar_string(session, seeded) -> None:
    field_id = seeded["field_ids"]["author"]
    spec = _spec(
        metadata=(MetadataCondition(field_id, FieldType.STRING, MetadataOp.EQ, "Bob Smith"),)
    )
    assert await _labels(session, seeded, spec) == ["D2"]


async def test_metadata_contains_scalar_string(session, seeded) -> None:
    field_id = seeded["field_ids"]["author"]
    spec = _spec(
        metadata=(MetadataCondition(field_id, FieldType.STRING, MetadataOp.CONTAINS, "Ada"),),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, spec) == ["D1", "D5", "D3"]  # alpha < epsilon < gamma


async def test_metadata_in_scalar_int(session, seeded) -> None:
    field_id = seeded["field_ids"]["year"]
    spec = _spec(
        metadata=(MetadataCondition(field_id, FieldType.INTEGER, MetadataOp.IN, [2020, 2022]),),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, spec) == ["D1", "D4"]


async def test_metadata_in_string_list_uses_has_any(session, seeded) -> None:
    """keyword_list IN — Postgres ``?|`` over the array's string elements."""
    field_id = seeded["field_ids"]["tags"]
    spec = _spec(
        metadata=(MetadataCondition(field_id, FieldType.KEYWORD_LIST, MetadataOp.IN, ["vision"]),),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, spec) == ["D4", "D3"]  # delta < gamma


async def test_metadata_in_number_list_uses_containment_not_has_any(session, seeded) -> None:
    """integer_list IN — MUST use JSONB ``@>``: a ``?|`` on numbers silently matches nothing."""
    field_id = seeded["field_ids"]["ratings"]
    spec = _spec(
        metadata=(MetadataCondition(field_id, FieldType.INTEGER_LIST, MetadataOp.IN, [7]),),
    )
    assert await _labels(session, seeded, spec) == ["D4"]

    # A second value proves it isn't coincidentally matching everything.
    spec_one = _spec(
        metadata=(MetadataCondition(field_id, FieldType.INTEGER_LIST, MetadataOp.IN, [1]),),
    )
    assert await _labels(session, seeded, spec_one) == ["D1"]


async def test_metadata_gte_lte_numeric_float(session, seeded) -> None:
    field_id = seeded["field_ids"]["score"]
    gte = _spec(
        metadata=(MetadataCondition(field_id, FieldType.FLOAT, MetadataOp.GTE, 4.0),),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, gte) == ["D2", "D4"]

    lte = _spec(metadata=(MetadataCondition(field_id, FieldType.FLOAT, MetadataOp.LTE, 3.0),))
    assert await _labels(session, seeded, lte) == ["D3"]


async def test_metadata_gte_lte_datetime(session, seeded) -> None:
    """Regression for the shipped bug: the GTE/LTE bound arrives as a plain STRING for DATETIME
    fields (``MetadataFilter.value: Any`` never coerces JSON strings to ``datetime``), and the SQL
    used to compare ``CAST(... AS TIMESTAMP) >= $1::VARCHAR`` — an operator Postgres doesn't have.
    ``document_query.py::_value_predicate`` now casts the bound value too (see ``_typed_value``)."""
    field_id = seeded["field_ids"]["published_at"]
    spec = _spec(
        metadata=(
            MetadataCondition(field_id, FieldType.DATETIME, MetadataOp.GTE, "2021-01-01T00:00:00"),
        ),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, spec) == ["D2", "D4", "D5"]


async def test_metadata_gte_lte_numeric_bound_sent_as_string(session, seeded) -> None:
    """Same asymmetry class, numeric side: ``MetadataFilter.value: Any`` places no constraint on the
    wire type, so a client (or a JSON-string-typed form field) can send "4.0" instead of 4.0 for a
    FLOAT field's GTE/LTE bound. Before the fix this would compare ``NUMERIC >= VARCHAR`` — no such
    Postgres operator — even though the happy path (a real JSON number) worked, masking the bug."""
    field_id = seeded["field_ids"]["score"]
    spec = _spec(
        metadata=(MetadataCondition(field_id, FieldType.FLOAT, MetadataOp.GTE, "4.0"),),
        sort=SortSpec(column="filename", direction=SortDirection.ASC),
    )
    assert await _labels(session, seeded, spec) == ["D2", "D4"]


# -------------------- sort: numeric cast, not lexicographic --------------------


async def test_sort_by_base_column_asc_desc(session, seeded) -> None:
    asc = _spec(sort=SortSpec(column="page_count", direction=SortDirection.ASC))
    assert await _labels(session, seeded, asc) == ["D3", "D1", "D5", "D2", "D4"]

    desc = _spec(sort=SortSpec(column="page_count", direction=SortDirection.DESC))
    assert await _labels(session, seeded, desc) == ["D4", "D2", "D5", "D1", "D3"]


async def test_sort_by_metadata_field_is_numeric_not_text(session, seeded) -> None:
    """rank values (9, 10, 2, 100, 3) sort as 2 < 3 < 9 < 10 < 100 numerically; lexicographically
    ("10" < "100" < "2" < "3" < "9") they would come out wrong — this is exactly what
    ``compare_type``/``cast`` in ``_metadata_sort_key`` exists to prevent."""
    field_id = seeded["field_ids"]["rank"]
    spec = _spec(
        sort=SortSpec(
            column="rank",
            direction=SortDirection.ASC,
            metadata_field_id=field_id,
            metadata_field_type=FieldType.INTEGER,
        )
    )
    assert await _labels(session, seeded, spec) == ["D3", "D5", "D1", "D2", "D4"]


# -------------------- pagination + count --------------------


async def test_pagination_limit_offset_matches_count(session, seeded) -> None:
    spec = _spec(sort=SortSpec(column="filename", direction=SortDirection.ASC))
    total = await DocumentQueryApi.count(session, seeded["collection_id"], spec)
    assert total == 5

    rows = await DocumentQueryApi.query(session, seeded["collection_id"], spec, limit=2, offset=2)
    by_id = {doc_id: label for label, doc_id in seeded["doc_ids"].items()}
    # Full asc order is D1(alpha) D2(beta) D4(delta) D5(epsilon) D3(gamma) — offset 2, limit 2.
    assert [by_id[row.id] for row in rows] == ["D4", "D5"]
