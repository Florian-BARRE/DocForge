"""EXECUTES the DERIVED ``needs_reindex`` lifecycle against a real Postgres — the fix that replaced
the broken sticky one-way boolean (set True on any searchable-surface change, NEVER cleared).

Proven end to end, the exact cases the sticky flag got wrong:
  * (d) a NEVER-indexed collection (NULL ``indexed_signature``) never flags needs_reindex, however its
    config changes — nothing is indexed to be stale.
  * worker edge: a successful ingest advances ``indexed_signature`` to the current config + clears the
    flag (the ONLY thing that ever cleared it — the sticky boolean never did).
  * (a) a real semantic/lexical surface change against an indexed baseline flags needs_reindex True.
  * (b) REVERTING to the indexed config clears it back to False — the user's core bug.
  * (c) a ``filterable``-only toggle keeps it False (its payload index is reconciled live, no reindex).
  * (e) after the worker edge re-advances the baseline, the flag is False again.

Uses the PG-only facade paths (``apply_update`` / ``IngestionFacade._advance_indexed_baseline``), so
qdrant/s3 are never touched (passed as None); every read is id-scoped, so the tests are order-free.
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
from shared_libs.services.db.facades.ingestion_facade import IngestionFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import Collection, MetadataField

pytestmark = pytest.mark.db


def _embed_blob() -> dict:
    """A minimal ingestion blob with one embed node — the embed-space half of the signature."""
    return {
        "nodes": [
            {
                "id": "embed_1",
                "kind": "bge_m3",
                "family": "embed",
                "config": {
                    "base_url": "http://bge:80",
                    "model": "bge-m3",
                    "embed_sparse": True,
                    "embed_semantic_fields": [],
                },
            }
        ]
    }


def _mf(name: str, *, ftype, semantic=False, lexical=False, filterable=False) -> MetadataField:
    """A fully-specified MetadataField (every NOT NULL flag set — transient rows get no DB defaults)."""
    return MetadataField(
        field_name=name,
        field_type=ftype,
        required=False,
        filterable=filterable,
        lexical=lexical,
        semantic=semantic,
        enum_values=None,
        origin=FieldOrigin.USER,
        scope=FieldScope.DOCUMENT,
    )


def _fields(*, author_semantic=False, year_filterable=False) -> list[MetadataField]:
    """The tunable two-field schema the lifecycle steps mutate (author vector flag, year filterable)."""
    return [
        _mf("author", ftype=FieldType.STRING, semantic=author_semantic),
        _mf("year", ftype=FieldType.INTEGER, filterable=year_filterable),
    ]


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    """A PostgresClient against the head-migrated throwaway db (disposed on teardown)."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _seed_collection(client: PostgresClient) -> uuid.UUID:
    """Create a collection (embed blob + two-field schema) via the facade; return its id."""
    facade = CollectionsFacade(client, None, None)
    collection = Collection(
        name=f"reindex-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
        pipeline=_embed_blob(),
        search={},
    )
    created = await facade.create(collection, _fields())
    return created.id


async def _read(client: PostgresClient, collection_id: uuid.UUID) -> tuple[bool, str | None]:
    """Return (needs_reindex, indexed_signature) straight from the row."""
    async with client.session() as session:
        row = await CollectionApi.get(session, collection_id)
        return row.needs_reindex, row.indexed_signature


async def _current_schema(client: PostgresClient, collection_id: uuid.UUID) -> list[MetadataField]:
    """The collection's current schema rows (for the worker-edge signature)."""
    async with client.session() as session:
        return await CollectionApi.get_schema(session, collection_id)


async def test_needs_reindex_full_lifecycle(client: PostgresClient) -> None:
    collection_id = await _seed_collection(client)
    collections = CollectionsFacade(client, None, None)
    ingestion = IngestionFacade(client, None, None)

    # (d) NEVER indexed: a semantic-surface change must NOT flag needs_reindex (nothing is stale).
    await collections.apply_update(
        collection_id,
        CollectionUpdateSpec(schema_fields=_fields(author_semantic=True)),
    )
    needs, signature = await _read(client, collection_id)
    assert needs is False and signature is None

    # Worker edge: a successful ingest stamps the baseline to the current config + clears the flag.
    await ingestion._advance_indexed_baseline(
        collection_id, await _current_schema(client, collection_id)
    )
    needs, baseline = await _read(client, collection_id)
    assert needs is False and baseline is not None

    # (a) A real surface change (author now lexical too) against the baseline flags needs_reindex.
    await collections.apply_update(
        collection_id,
        CollectionUpdateSpec(
            schema_fields=[
                _mf("author", ftype=FieldType.STRING, semantic=True, lexical=True),
                _mf("year", ftype=FieldType.INTEGER),
            ]
        ),
    )
    needs, _ = await _read(client, collection_id)
    assert needs is True

    # (b) REVERT to the indexed config (author semantic-only) clears it — the user's core bug.
    await collections.apply_update(
        collection_id,
        CollectionUpdateSpec(schema_fields=_fields(author_semantic=True)),
    )
    needs, _ = await _read(client, collection_id)
    assert needs is False

    # (c) A filterable-only toggle (year) keeps it False — reconciled live, no reindex.
    await collections.apply_update(
        collection_id,
        CollectionUpdateSpec(schema_fields=_fields(author_semantic=True, year_filterable=True)),
    )
    needs, _ = await _read(client, collection_id)
    assert needs is False

    # (e) Make it True again, then let the worker edge re-advance the baseline → False.
    await collections.apply_update(
        collection_id,
        CollectionUpdateSpec(schema_fields=_fields(author_semantic=False)),
    )
    needs, _ = await _read(client, collection_id)
    assert needs is True
    await ingestion._advance_indexed_baseline(
        collection_id, await _current_schema(client, collection_id)
    )
    needs, _ = await _read(client, collection_id)
    assert needs is False
