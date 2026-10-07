"""EXECUTES the schema field-ops data path against a real Postgres (qdrant/s3 None):
* a RENAME is an in-place UPDATE of ``field_name`` — the field keeps its id, so its stored
  ``document_metadata`` rows survive, and a ``title_field`` naming it follows the new name;
* a REMOVE cascades its values away, and ``SchemaChangeFacade.count_field_values`` measured them first;
* a rename SWAP (a↔b) applies without tripping the (collection, field_name) UNIQUE constraint.
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import select

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import CollectionUpdateSpec, SchemaChangeFacade
from shared_libs.services.db.facades.collections_facade import CollectionsFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentMetadata,
    DocumentStatus,
    MetadataField,
    SourceKind,
)

pytestmark = pytest.mark.db


def _mf(name: str) -> MetadataField:
    """A fully-specified document-scope field (transient rows get no DB defaults)."""
    return MetadataField(
        field_name=name,
        field_type=FieldType.STRING,
        required=False,
        filterable=False,
        lexical=False,
        semantic=False,
        enum_values=None,
        origin=FieldOrigin.USER,
        scope=FieldScope.DOCUMENT,
        description=None,
    )


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    """A PostgresClient against the head-migrated throwaway db (disposed on teardown)."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _seed(client: PostgresClient) -> uuid.UUID:
    """A collection with fields author/old/keep, one document carrying a value for each."""
    created = await CollectionsFacade(client, None, None).create(
        Collection(
            name=f"ops-{uuid.uuid4().hex[:8]}",
            supported_formats=["pdf"],
            max_file_size_bytes=10_000_000,
            pipeline={},
            search={},
            title_field="author",
        ),
        [_mf("author"), _mf("old"), _mf("keep")],
    )
    async with client.session() as session:
        fields = {f.field_name: f for f in await CollectionApi.get_schema(session, created.id)}
        document = Document(
            collection_id=created.id,
            source_hash=f"h-{uuid.uuid4().hex}",
            filename="d.pdf",
            format="pdf",
            mime_type="application/pdf",
            file_size=1,
            source_kind=SourceKind.DIGITAL_BORN,
            status=DocumentStatus.DONE,
            pipeline_version="v1",
        )
        session.add(document)
        await session.flush()
        for name in ("author", "old", "keep"):
            session.add(
                DocumentMetadata(
                    document_id=document.id,
                    field_id=fields[name].id,
                    value=f"{name}-value",
                    origin=FieldOrigin.USER,
                )
            )
    return created.id


async def _values(client: PostgresClient, collection_id: uuid.UUID) -> dict[str, list]:
    """field name → its stored document values."""
    async with client.session() as session:
        rows = await session.execute(
            select(MetadataField.field_name, DocumentMetadata.value)
            .join(DocumentMetadata, DocumentMetadata.field_id == MetadataField.id)
            .where(MetadataField.collection_id == collection_id)
        )
        out: dict[str, list] = {}
        for name, value in rows:
            out.setdefault(name, []).append(value)
        return out


async def test_rename_keeps_values_and_title_follows_remove_cascades(
    client: PostgresClient,
) -> None:
    collection_id = await _seed(client)
    assert await SchemaChangeFacade(client, None).count_field_values(collection_id, ["old"]) == {
        "old": 1
    }

    await CollectionsFacade(client, None, None).apply_update(
        collection_id,
        CollectionUpdateSpec(
            schema_fields=[_mf("writer"), _mf("keep")], schema_renames={"author": "writer"}
        ),
    )

    assert await _values(client, collection_id) == {
        "writer": ["author-value"],
        "keep": ["keep-value"],
    }
    async with client.session() as session:
        row = await CollectionApi.get(session, collection_id)
    assert row.title_field == "writer"


async def test_rename_swap_applies_without_a_unique_collision(client: PostgresClient) -> None:
    collection_id = await _seed(client)
    await CollectionsFacade(client, None, None).apply_update(
        collection_id,
        CollectionUpdateSpec(
            schema_fields=[_mf("old"), _mf("author"), _mf("keep")],
            schema_renames={"author": "old", "old": "author"},
        ),
    )
    values = await _values(client, collection_id)
    assert values["old"] == ["author-value"] and values["author"] == ["old-value"]
