"""EXECUTES the agent-UX schema settings against a real Postgres (PG-only facade paths, qdrant/s3 None):
* a field ``description`` is persisted on create and updated by a description-only schema PATCH that
  leaves ``needs_reindex`` untouched (description is outside the index signature);
* ``title_field`` is persisted by the atomic PATCH, and a later schema PATCH that REMOVES that field
  clears it to NULL in the same transaction (soft reference, never blocking the schema edit).
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import CollectionUpdateSpec
from shared_libs.services.db.facades.collections_facade import CollectionsFacade
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import Collection, MetadataField

pytestmark = pytest.mark.db


def _mf(name: str, *, description: str | None = None, semantic: bool = False) -> MetadataField:
    """A fully-specified document-scope field (transient rows get no DB defaults)."""
    return MetadataField(
        field_name=name,
        field_type=FieldType.STRING,
        required=False,
        filterable=False,
        lexical=False,
        semantic=semantic,
        enum_values=None,
        origin=FieldOrigin.USER,
        scope=FieldScope.DOCUMENT,
        description=description,
    )


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    """A PostgresClient against the head-migrated throwaway db (disposed on teardown)."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _seed(facade: CollectionsFacade) -> uuid.UUID:
    created = await facade.create(
        Collection(
            name=f"title-{uuid.uuid4().hex[:8]}",
            supported_formats=["pdf"],
            max_file_size_bytes=10_000_000,
            pipeline={},
            search={},
        ),
        [_mf("topic", description="Business process", semantic=True), _mf("author")],
    )
    return created.id


async def _state(client: PostgresClient, collection_id: uuid.UUID):
    async with client.session() as session:
        row = await CollectionApi.get(session, collection_id)
        schema = await CollectionApi.get_schema(session, collection_id)
        return row, {f.field_name: f.description for f in schema}


async def test_description_persists_and_never_flags_reindex(client: PostgresClient) -> None:
    facade = CollectionsFacade(client, None, None)
    collection_id = await _seed(facade)
    _, descriptions = await _state(client, collection_id)
    assert descriptions == {"topic": "Business process", "author": None}

    # Give the collection an indexed baseline (its current signature) so a real surface change
    # WOULD flag a reindex — a description-only edit must not.
    async with client.session() as session:
        row = await CollectionApi.get(session, collection_id)
        schema = await CollectionApi.get_schema(session, collection_id)
        row.indexed_signature = CollectionIndexSignature.compute(row.pipeline, schema)

    result = await facade.apply_update(
        collection_id,
        CollectionUpdateSpec(
            schema_fields=[
                _mf("topic", description="Procurement step", semantic=True),
                _mf("author"),
            ]
        ),
    )

    row, descriptions = await _state(client, collection_id)
    assert descriptions["topic"] == "Procurement step"
    assert result.schema_reindex_required is False
    assert row.needs_reindex is False


async def test_title_field_set_then_cleared_when_its_field_is_removed(
    client: PostgresClient,
) -> None:
    facade = CollectionsFacade(client, None, None)
    collection_id = await _seed(facade)

    await facade.apply_update(
        collection_id, CollectionUpdateSpec(apply_title_field=True, title_field="topic")
    )
    row, _ = await _state(client, collection_id)
    assert row.title_field == "topic"

    # A schema edit dropping "topic" is not blocked — it clears the orphaned setting atomically.
    await facade.apply_update(collection_id, CollectionUpdateSpec(schema_fields=[_mf("author")]))
    row, descriptions = await _state(client, collection_id)
    assert list(descriptions) == ["author"]
    assert row.title_field is None
