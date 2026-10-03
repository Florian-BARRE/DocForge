"""EXECUTES DocumentApi.update_metadata / delete_metadata against a real Postgres.

The serviceless tests only inspect the compiled statements; only a real DB proves the upsert's
ON CONFLICT target, that a delete touches ONLY the listed (document, field) rows, that another
document's value for the same field is untouched, and that a NUL is stripped before Postgres can
reject it. The NUL is built with ``chr(0)`` so this file never holds a raw null byte.
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.postgresql.apis import DocumentApi
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentMetadata,
    DocumentStatus,
    MetadataField,
    SourceKind,
)

pytestmark = pytest.mark.db

_NUL = chr(0)


@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            yield db_session
    finally:
        await engine.dispose()


async def _seed(db_session: AsyncSession) -> tuple[list[uuid.UUID], dict[str, int]]:
    """One collection, three fields (a, b, c) and TWO documents; returns ([doc1, doc2], {name: id})."""
    collection = Collection(
        name=f"meta-edit-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
    )
    db_session.add(collection)
    await db_session.flush()
    fields = {
        name: MetadataField(
            collection_id=collection.id,
            field_name=name,
            field_type=FieldType.TEXT,
            required=False,
            origin=FieldOrigin.USER,
            scope=FieldScope.DOCUMENT,
        )
        for name in ("a", "b", "c")
    }
    db_session.add_all(fields.values())
    documents = [
        Document(
            collection_id=collection.id,
            source_hash=f"hash-{uuid.uuid4().hex}",
            filename=f"doc{i}.pdf",
            format="pdf",
            mime_type="application/pdf",
            file_size=1,
            source_kind=SourceKind.DIGITAL_BORN,
            status=DocumentStatus.DONE,
            pipeline_version="v1",
        )
        for i in range(2)
    ]
    db_session.add_all(documents)
    await db_session.flush()
    ids = [doc.id for doc in documents]
    field_ids = {name: f.id for name, f in fields.items()}
    for doc_id in ids:
        for name, field_id in field_ids.items():
            db_session.add(
                DocumentMetadata(
                    document_id=doc_id,
                    field_id=field_id,
                    value=f"{name}-original",
                    origin=FieldOrigin.USER,
                )
            )
    await db_session.commit()
    return ids, field_ids


async def _values(db_session: AsyncSession, doc_id: uuid.UUID, field_ids: dict[str, int]):
    db_session.expire_all()
    rows = await DocumentApi.get_metadata(db_session, doc_id)
    by_id = {r.field_id: r.value for r in rows}
    return {name: by_id.get(fid) for name, fid in field_ids.items()}


async def test_delete_metadata_removes_only_the_listed_fields_of_that_document(
    session: AsyncSession,
) -> None:
    (doc1, doc2), fields = await _seed(session)

    await DocumentApi.delete_metadata(session, doc1, [fields["a"], fields["c"]])
    await session.commit()

    assert await _values(session, doc1, fields) == {"a": None, "b": "b-original", "c": None}
    # The OTHER document's rows for the very same fields are untouched.
    assert await _values(session, doc2, fields) == {
        "a": "a-original",
        "b": "b-original",
        "c": "c-original",
    }


async def test_delete_metadata_with_empty_list_deletes_nothing(session: AsyncSession) -> None:
    (doc1, _), fields = await _seed(session)

    await DocumentApi.delete_metadata(session, doc1, [])
    await session.commit()

    assert all(v is not None for v in (await _values(session, doc1, fields)).values())


async def test_delete_metadata_ignores_a_field_with_no_stored_value(session: AsyncSession) -> None:
    (doc1, _), fields = await _seed(session)
    await DocumentApi.delete_metadata(session, doc1, [fields["a"]])
    await session.commit()

    # Deleting the already-absent row again (plus an unknown id) is a harmless no-op.
    await DocumentApi.delete_metadata(session, doc1, [fields["a"], 10**9])
    await session.commit()

    assert await _values(session, doc1, fields) == {"a": None, "b": "b-original", "c": "c-original"}


async def test_update_metadata_upserts_only_listed_fields_and_strips_nul(
    session: AsyncSession,
) -> None:
    (doc1, doc2), fields = await _seed(session)
    # Clear "c" first so the same call exercises BOTH the overwrite (a) and the insert (c) halves.
    await DocumentApi.delete_metadata(session, doc1, [fields["c"]])
    await session.commit()

    await DocumentApi.update_metadata(
        session,
        doc1,
        [
            DocumentMetadata(field_id=fields["a"], value=f"new{_NUL}-a", origin=FieldOrigin.USER),
            DocumentMetadata(field_id=fields["c"], value="fresh-c", origin=FieldOrigin.GENERATED),
        ],
    )
    await session.commit()

    assert await _values(session, doc1, fields) == {
        "a": "new-a",  # overwritten in place, NUL stripped
        "b": "b-original",  # unlisted -> untouched
        "c": "fresh-c",  # inserted
    }
    # Origin follows the written row; the other document is unaffected.
    session.expire_all()
    origin_c = await session.scalar(
        select(DocumentMetadata.origin).where(
            DocumentMetadata.document_id == doc1, DocumentMetadata.field_id == fields["c"]
        )
    )
    assert origin_c == FieldOrigin.GENERATED
    assert (await _values(session, doc2, fields))["a"] == "a-original"
    # The upsert did not duplicate the (document, field) row.
    rows = await DocumentApi.get_metadata(session, doc1)
    assert len(rows) == 3
