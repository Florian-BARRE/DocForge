"""EXECUTES the contains / prefix filter-operator expansion against a real Postgres: case-insensitive
matching returning every stored case variant, `%` and `_` taken as LITERAL characters (a naive LIKE
would treat them as wildcards), keyword_list element explosion, per-field (hence per-collection)
isolation, the bounded limit, and the SearchFilterResolver end to end — a pattern covering more than
MAX_PATTERN_VALUES stored values is a 422 (never a silently narrowed filter)."""

# ====== Standard Library Imports ======
import pathlib
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import MetadataValueResolver
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentMetadata,
    DocumentStatus,
    MetadataField,
    SourceKind,
)

pytestmark = pytest.mark.db

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"
_CODES = ["Alpha", "alpha", "ALPHABET", "beta", "50%_off", "500 off", "a_c", "abc"]


@pytest.fixture
def app_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put app/ on sys.path for the app-side resolver (like tests/units/search/conftest.py)."""
    monkeypatch.syspath_prepend(str(APP_DIR))


@pytest.fixture
async def seeded(migrated_db_dsn: str) -> AsyncIterator[tuple[MetadataValueResolver, dict]]:
    engine = create_async_engine(migrated_db_dsn)
    client = PostgresClient(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as session:
            fields = await _seed(session)
        yield MetadataValueResolver(client), fields
    finally:
        await client.dispose()
        await engine.dispose()


def _document(collection_id: uuid.UUID, i: int) -> Document:
    return Document(
        collection_id=collection_id,
        source_hash=f"h-{uuid.uuid4().hex}",
        filename=f"d{i}.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.DONE,
        pipeline_version="v1",
    )


async def _seed(session: AsyncSession) -> dict[str, SimpleNamespace]:
    collections = [
        Collection(
            name=f"patterns-{uuid.uuid4().hex[:8]}",
            supported_formats=["pdf"],
            max_file_size_bytes=1,
        )
        for _ in range(2)
    ]
    session.add_all(collections)
    await session.flush()
    own, other = collections[0].id, collections[1].id
    rows = {
        "code": MetadataField(
            collection_id=own,
            field_name="code",
            field_type=FieldType.STRING,
            origin=FieldOrigin.USER,
            scope=FieldScope.DOCUMENT,
        ),
        "tags": MetadataField(
            collection_id=own,
            field_name="tags",
            field_type=FieldType.KEYWORD_LIST,
            origin=FieldOrigin.USER,
            scope=FieldScope.DOCUMENT,
        ),
        "many": MetadataField(
            collection_id=own,
            field_name="many",
            field_type=FieldType.KEYWORD_LIST,
            origin=FieldOrigin.USER,
            scope=FieldScope.DOCUMENT,
        ),
        "other_code": MetadataField(
            collection_id=other,
            field_name="code",
            field_type=FieldType.STRING,
            origin=FieldOrigin.USER,
            scope=FieldScope.DOCUMENT,
        ),
    }
    session.add_all(rows.values())
    docs = [_document(own, i) for i in range(len(_CODES))] + [_document(other, 99)]
    session.add_all(docs)
    await session.flush()
    for doc, code in zip(docs, _CODES, strict=False):
        session.add(
            DocumentMetadata(
                document_id=doc.id, field_id=rows["code"].id, value=code, origin=FieldOrigin.USER
            )
        )
    session.add(
        DocumentMetadata(
            document_id=docs[0].id,
            field_id=rows["tags"].id,
            value=["Gamma", "GAMMA-ray"],
            origin=FieldOrigin.USER,
        )
    )
    # 600 distinct values sharing the prefix "item-" — past MAX_PATTERN_VALUES (500).
    session.add(
        DocumentMetadata(
            document_id=docs[0].id,
            field_id=rows["many"].id,
            value=[f"item-{i:04d}" for i in range(600)],
            origin=FieldOrigin.USER,
        )
    )
    # The other collection stores a matching value that must never leak into the first one.
    session.add(
        DocumentMetadata(
            document_id=docs[-1].id,
            field_id=rows["other_code"].id,
            value="alpha-other",
            origin=FieldOrigin.USER,
        )
    )
    specs = {
        name: SimpleNamespace(
            id=f.id,
            scope=f.scope,
            field_name=f.field_name,
            field_type=f.field_type,
            filterable=True,
        )
        for name, f in rows.items()
    }
    await session.commit()
    return specs


async def test_prefix_is_case_insensitive_and_returns_every_variant(seeded) -> None:
    resolver, fields = seeded
    assert sorted(await resolver.prefix(fields["code"], "AL", 10)) == ["ALPHABET", "Alpha", "alpha"]


async def test_contains_is_case_insensitive(seeded) -> None:
    resolver, fields = seeded
    assert sorted(await resolver.contains(fields["code"], "pHa", 10)) == [
        "ALPHABET",
        "Alpha",
        "alpha",
    ]


async def test_percent_and_underscore_are_literal_characters(seeded) -> None:
    resolver, fields = seeded
    # A LIKE '50%%' would also match "500 off"; a LIKE 'a_c%' would also match "abc".
    assert await resolver.prefix(fields["code"], "50%", 10) == ["50%_off"]
    assert await resolver.contains(fields["code"], "%_", 10) == ["50%_off"]
    assert await resolver.prefix(fields["code"], "a_c", 10) == ["a_c"]
    assert await resolver.contains(fields["code"], "_", 10) == ["50%_off", "a_c"]


async def test_patterns_explode_keyword_list_elements(seeded) -> None:
    resolver, fields = seeded
    assert sorted(await resolver.prefix(fields["tags"], "gamma", 10)) == ["GAMMA-ray", "Gamma"]


async def test_patterns_are_scoped_to_the_collection_field(seeded) -> None:
    resolver, fields = seeded
    assert "alpha-other" not in await resolver.contains(fields["code"], "alpha", 10)
    assert await resolver.contains(fields["other_code"], "alpha", 10) == ["alpha-other"]


async def test_no_match_is_empty_and_limit_bounds_the_read(seeded) -> None:
    resolver, fields = seeded
    assert await resolver.contains(fields["code"], "zzz", 10) == []
    assert len(await resolver.prefix(fields["many"], "item-", 7)) == 7


async def test_resolver_expands_a_prefix_to_the_stored_values(seeded, app_path) -> None:
    from backend.libs.search import SearchFilterResolver  # noqa: PLC0415

    resolver, fields = seeded
    resolution = await SearchFilterResolver(resolver).resolve(
        {"code": {"prefix": "al"}}, [fields["code"]]
    )
    assert sorted(resolution.filters["code"]["in"]) == ["ALPHABET", "Alpha", "alpha"]
    assert resolution.hints == []


async def test_resolver_rejects_a_pattern_past_the_cap_with_422(seeded, app_path) -> None:
    from backend.libs.search import SearchFilterResolver  # noqa: PLC0415

    resolver, fields = seeded
    with pytest.raises(HTTPException) as caught:
        await SearchFilterResolver(resolver).resolve({"many": {"prefix": "ITEM"}}, [fields["many"]])
    assert caught.value.status_code == 422
    assert "more than 500" in caught.value.detail
