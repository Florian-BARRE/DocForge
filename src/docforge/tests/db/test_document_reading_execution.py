"""EXECUTES the document-reading reads against a real Postgres (PG-only facade, qdrant/s3 None): the
heading-only outline read (reading order, page → None on a page-less document), the text-free chunk
index (order, role/override, NULL heading_path coalesced), the chunk count and the limit/offset page
of the chunk listing."""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import DocumentsFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.tables import (
    Block,
    Chunk,
    ChunkBlock,
    Collection,
    Document,
    DocumentStatus,
    SourceKind,
)

pytestmark = pytest.mark.db


def _document(collection_id: uuid.UUID, page_count: int | None) -> Document:
    return Document(
        collection_id=collection_id,
        source_hash=f"h-{uuid.uuid4().hex}",
        filename="d.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.DONE,
        pipeline_version="v1",
        page_count=page_count,
    )


def _block(document_id: uuid.UUID, key: str, block_type: str, page: int, order: int) -> Block:
    return Block(
        id=f"{document_id}:{key}",
        document_id=document_id,
        block_type=block_type,
        page=page,
        bbox=[0.0, 0.0, 1.0, 1.0],
        reading_order=order,
        level=2 if block_type == "heading" else None,
        text=key,
    )


def _chunk(document_id: uuid.UUID, index: int, **extra) -> Chunk:
    return Chunk(
        id=uuid.uuid4(),
        document_id=document_id,
        config_hash="c",
        chunk_index=index,
        strategy="s",
        text=f"t{index}",
        token_count=1,
        **extra,
    )


@pytest.fixture
async def seeded(migrated_db_dsn: str) -> AsyncIterator[tuple[DocumentsFacade, dict]]:
    engine = create_async_engine(migrated_db_dsn)
    client = PostgresClient(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as session:
            collection = Collection(
                name=f"reading-{uuid.uuid4().hex[:8]}",
                supported_formats=["pdf"],
                max_file_size_bytes=1,
            )
            session.add(collection)
            await session.flush()
            paged = _document(collection.id, page_count=3)
            pageless = _document(collection.id, page_count=0)
            session.add_all([paged, pageless])
            await session.flush()
            session.add_all(
                [
                    _block(paged.id, "Second", "heading", 2, 5),
                    _block(paged.id, "body", "paragraph", 0, 1),
                    _block(paged.id, "First", "heading", 0, 0),
                    _block(pageless.id, "Only", "heading", 0, 0),
                ]
            )
            chunks = [
                _chunk(paged.id, 2, role="toc", enabled_override=True, heading_path=["S"]),
                _chunk(paged.id, 0, heading_path=["First"]),
                _chunk(paged.id, 1),
            ]
            session.add_all(chunks)
            await session.flush()
            # Chunk 0 holds reading orders 0-1, chunk 2 holds 5, chunk 1 has no composition.
            session.add_all(
                [
                    ChunkBlock(chunk_id=chunks[1].id, block_id=f"{paged.id}:First", position=0),
                    ChunkBlock(chunk_id=chunks[1].id, block_id=f"{paged.id}:body", position=1),
                    ChunkBlock(chunk_id=chunks[0].id, block_id=f"{paged.id}:Second", position=0),
                ]
            )
            ids = {"paged": paged.id, "pageless": pageless.id}
            await session.commit()
        yield DocumentsFacade(client, None, None), ids
    finally:
        await client.dispose()
        await engine.dispose()


async def test_headings_in_reading_order_with_pageless_page_none(seeded) -> None:
    facade, ids = seeded

    headings = await facade.get_headings(ids["paged"])
    assert [(h.text, h.level, h.page, h.reading_order) for h in headings] == [
        ("First", 2, 0, 0),
        ("Second", 2, 2, 5),
    ]
    assert [(h.text, h.page) for h in await facade.get_headings(ids["pageless"])] == [
        ("Only", None)
    ]


async def test_chunk_index_is_ordered_and_text_free(seeded) -> None:
    facade, ids = seeded

    index = await facade.get_chunk_index(ids["paged"])

    assert [
        (e.chunk_index, e.role, e.enabled_override, e.heading_path, e.last_reading_order)
        for e in index
    ] == [
        (0, "body", None, ["First"], 1),
        (1, "body", None, [], None),
        (2, "toc", True, ["S"], 5),
    ]


async def test_chunk_count_and_limit_offset_page(seeded) -> None:
    facade, ids = seeded

    assert await facade.count_chunks(ids["paged"]) == 3
    page = await facade.get_chunks(ids["paged"], limit=1, offset=1)
    assert [c.chunk_index for c in page] == [1]
    assert [c.chunk_index for c in await facade.get_chunks(ids["paged"], offset=2)] == [2]
    assert [c.chunk_index for c in await facade.get_chunks(ids["paged"])] == [0, 1, 2]
