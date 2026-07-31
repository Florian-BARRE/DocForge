"""The chunk block-location read resolves a chunk's page from its primary block, but must return
None for a PAGE-LESS document (an HTML doc with no page render, whose blocks carry the placeholder
page index 0). The document's page_count is the discriminator: a falsy count (0 or NULL) → None; a
positive count keeps the genuine 0-based page index (page 0 is a real first page). Postgres mocked."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.postgresql.apis.chunk_api import ChunkApi


def _session_returning(rows: list[tuple]) -> MagicMock:
    """A session mock whose execute() yields a result whose .all() returns ``rows``."""
    result = MagicMock()
    result.all.return_value = rows
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


async def test_pageless_document_page_is_nulled_paged_zero_index_preserved() -> None:
    """page_count falsy (0 / NULL) → page None; page_count positive → the 0-based index is kept."""
    cid = uuid.uuid4()
    # rows: (chunk_id, block_id, page, bbox, page_count)
    rows = [
        (cid, "d:#/texts/0", 0, [0.0, 0.0, 1.0, 1.0], 5),  # paged doc, first page → 0 preserved
        (cid, "d:#/texts/1", 3, [0.0, 0.0, 1.0, 1.0], 5),  # paged doc, page 3 → preserved
        (cid, "d:#/texts/2", 0, [0.0, 0.0, 1.0, 1.0], 0),  # page-less (count 0) → None
        (cid, "d:#/texts/3", 0, [0.0, 0.0, 1.0, 1.0], None),  # page-less (count NULL) → None
    ]
    out = await ChunkApi.get_block_locations_for_chunks(_session_returning(rows), [cid])

    assert [row[2] for row in out] == [0, 3, None, None]
    # bbox and identity pass through untouched — only the page is conditionally nulled.
    assert out[0][1] == "d:#/texts/0" and out[0][3] == [0.0, 0.0, 1.0, 1.0]


async def test_no_chunk_ids_short_circuits() -> None:
    """An empty id set never touches the session (no pointless round-trip)."""
    session = MagicMock()
    session.execute = AsyncMock()
    assert await ChunkApi.get_block_locations_for_chunks(session, []) == []
    session.execute.assert_not_awaited()
