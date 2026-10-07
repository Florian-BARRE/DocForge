"""EXECUTES MetadataValueResolver against a real Postgres: the JSONB element explosion (scalar AND
keyword_list values), case-insensitive canonicalization returning every stored variant, the
suggestion ordering (prefix > contains > similarity), distinct values/count, the chunk-scope table
path, the per-field (hence per-collection) scoping and the batched title-field read."""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import MetadataValueResolver
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.tables import (
    Chunk,
    ChunkMetadata,
    Collection,
    Document,
    DocumentMetadata,
    DocumentStatus,
    MetadataField,
    SourceKind,
)

pytestmark = pytest.mark.db


@pytest.fixture
async def seeded(migrated_db_dsn: str) -> AsyncIterator[tuple[MetadataValueResolver, dict]]:
    engine = create_async_engine(migrated_db_dsn)
    client = PostgresClient(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as session:
            fields, docs = await _seed(session)
        yield MetadataValueResolver(client), {"fields": fields, "docs": docs}
    finally:
        await client.dispose()
        await engine.dispose()


def _field(collection_id, name, ftype, scope=FieldScope.DOCUMENT) -> MetadataField:
    origin = FieldOrigin.GENERATED if scope == FieldScope.CHUNK else FieldOrigin.USER
    return MetadataField(
        collection_id=collection_id, field_name=name, field_type=ftype, origin=origin, scope=scope
    )


async def _seed(session: AsyncSession) -> tuple[dict[str, SimpleNamespace], list[uuid.UUID]]:
    collections = [
        Collection(
            name=f"values-{uuid.uuid4().hex[:8]}", supported_formats=["pdf"], max_file_size_bytes=1
        )
        for _ in range(2)
    ]
    session.add_all(collections)
    await session.flush()
    own, other = collections[0].id, collections[1].id
    fields = {
        "ident": _field(own, "ident", FieldType.STRING),
        "tags": _field(own, "tags", FieldType.KEYWORD_LIST),
        "topic": _field(own, "topic", FieldType.STRING, FieldScope.CHUNK),
        "codes": _field(own, "codes", FieldType.KEYWORD_LIST),
        "other_ident": _field(other, "ident", FieldType.STRING),
    }
    session.add_all(fields.values())
    docs = [
        Document(
            collection_id=own if i < 4 else other,
            source_hash=f"h-{uuid.uuid4().hex}",
            filename=f"d{i}.pdf",
            format="pdf",
            mime_type="application/pdf",
            file_size=1,
            source_kind=SourceKind.DIGITAL_BORN,
            status=DocumentStatus.DONE,
            pipeline_version="v1",
        )
        for i in range(5)
    ]
    session.add_all(docs)
    await session.flush()
    idents = ["AFD-P0153", "afd-P0153", "AFD-P0154", "AFD-P0154"]
    tags = [["Audit", "Law"], ["audit"], ["Finance"], ["Law"]]
    for doc, ident, tag in zip(docs[:4], idents, tags, strict=True):
        session.add(
            DocumentMetadata(
                document_id=doc.id,
                field_id=fields["ident"].id,
                value=ident,
                origin=FieldOrigin.USER,
            )
        )
        session.add(
            DocumentMetadata(
                document_id=doc.id, field_id=fields["tags"].id, value=tag, origin=FieldOrigin.USER
            )
        )
    # 60 values x 2 case variants = 120 stored elements — past the old 100-row batch-wide cap.
    session.add(
        DocumentMetadata(
            document_id=docs[0].id,
            field_id=fields["codes"].id,
            value=[code for i in range(60) for code in (f"c{i:03d}", f"C{i:03d}")],
            origin=FieldOrigin.USER,
        )
    )
    # The other collection stores a variant that must never leak into the first one's answers.
    session.add(
        DocumentMetadata(
            document_id=docs[4].id,
            field_id=fields["other_ident"].id,
            value="AFD-p0153",
            origin=FieldOrigin.USER,
        )
    )
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=docs[0].id,
        config_hash="c",
        chunk_index=0,
        strategy="s",
        text="t",
        token_count=1,
    )
    session.add(chunk)
    await session.flush()
    session.add(ChunkMetadata(chunk_id=chunk.id, field_id=fields["topic"].id, value="Governance"))
    # Detach plain specs BEFORE commit expires the ORM rows (the resolver only reads id + scope).
    specs = {
        name: SimpleNamespace(id=f.id, scope=f.scope, field_name=f.field_name)
        for name, f in fields.items()
    }
    doc_ids = [doc.id for doc in docs]
    await session.commit()
    return specs, doc_ids


async def test_canonicalize_returns_every_case_variant_scoped_to_the_field(seeded) -> None:
    resolver, data = seeded
    result = await resolver.canonicalize(data["fields"]["ident"], ["afd-p0153", "nope"])
    assert result == {"afd-p0153": ["AFD-P0153", "afd-P0153"], "nope": []}


async def test_canonicalize_caps_variants_per_value_not_per_batch(seeded) -> None:
    """A batch-wide LIMIT ordered by value truncated the LATE values of a large batch (false "no
    match" → narrowed results); the cap is per value, so every value keeps its variants."""
    resolver, data = seeded
    requested = [f"c{i:03d}" for i in range(60)]
    result = await resolver.canonicalize(data["fields"]["codes"], requested)
    assert result == {value: [value.upper(), value] for value in requested}


async def test_canonicalize_explodes_keyword_list_elements(seeded) -> None:
    resolver, data = seeded
    assert await resolver.canonicalize(data["fields"]["tags"], "AUDIT") == {
        "AUDIT": ["Audit", "audit"]
    }


async def test_canonicalize_reads_the_chunk_scope_table(seeded) -> None:
    resolver, data = seeded
    assert await resolver.canonicalize(data["fields"]["topic"], "governance") == {
        "governance": ["Governance"]
    }


async def test_suggest_orders_prefix_then_contains_then_similarity(seeded) -> None:
    resolver, data = seeded
    # Containment: both idents contain "p015"; the more frequent / shorter ranks first.
    assert await resolver.suggest(data["fields"]["ident"], "P015", k=2) == [
        "AFD-P0154",
        "AFD-P0153",
    ]
    # No containment → difflib similarity over the bounded pool.
    assert (await resolver.suggest(data["fields"]["ident"], "afd-p0153x", k=5))[0].lower() == (
        "afd-p0153"
    )
    # Prefix beats a mid-string match.
    assert (await resolver.suggest(data["fields"]["tags"], "a", k=1)) == ["Audit"]


async def test_distinct_values_and_count(seeded) -> None:
    resolver, data = seeded
    assert await resolver.distinct_values(data["fields"]["tags"], limit=2) == ["Law", "Audit"]
    assert await resolver.distinct_count(data["fields"]["tags"]) == 4
    assert await resolver.distinct_count(data["fields"]["ident"]) == 3


async def test_document_values_batch_read(seeded) -> None:
    resolver, data = seeded
    docs = data["docs"]
    values = await resolver.document_values(data["fields"]["ident"], docs[:2])
    assert values == {docs[0]: "AFD-P0153", docs[1]: "afd-P0153"}
