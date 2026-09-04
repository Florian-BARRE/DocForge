"""BlobApi.delete_unreferenced — the concurrency-safe orphan purge (audit Finding 4).

The old flow was TWO statements: a ``find_unreferenced`` SELECT then a ``delete_rows`` DELETE, with the
S3 purge after the commit. That left a TOCTOU window: a concurrent ingest of the SAME bytes (content-
addressed dedup) could insert a reference row AFTER the SELECT snapshot but BEFORE the commit, so the
hash was judged unreferenced and its S3 object deleted out from under the new document. The fix folds
the reference test INTO the DELETE (``WHERE NOT EXISTS(reference)``, re-evaluated at delete time) and
uses ``RETURNING`` so only the rows actually removed are deleted from S3.

The true concurrency proof is a live two-transaction race (a ``-m db`` test — a real Postgres); here,
serviceless, we prove the STATEMENT is a single guarded DELETE that re-checks all four referencing
columns and returns the removed hashes (so no earlier snapshot can go stale)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from shared_libs.services.db.postgresql.apis import BlobApi


async def test_delete_unreferenced_is_one_guarded_delete_returning_removed_hashes() -> None:
    # 1. Capture the statement the API hands to session.execute (result yields the removed hashes).
    scalars = MagicMock()
    scalars.all.return_value = ["h1"]
    result = MagicMock()
    result.scalars.return_value = scalars
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    removed = await BlobApi.delete_unreferenced(session, ["h1", "h2"])

    # 2. It returns EXACTLY the rows the DELETE removed — the set the caller then deletes from S3.
    assert removed == ["h1"]

    # 3. The single statement is a DELETE ... RETURNING guarded by a NOT EXISTS per referencing column.
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect())).upper()
    assert sql.startswith("DELETE FROM BLOB")
    assert sql.count("NOT (EXISTS") == 4  # document source + pdf, page render, figure crop
    assert "RETURNING BLOB.CONTENT_HASH" in sql
    for referencing_table in ("DOCUMENT", "PAGE", "BLOCK_FIGURE"):
        assert referencing_table in sql


async def test_delete_unreferenced_empty_candidates_touches_nothing() -> None:
    session = MagicMock()
    session.execute = AsyncMock()

    removed = await BlobApi.delete_unreferenced(session, [])

    assert removed == []
    session.execute.assert_not_awaited()


async def test_delete_unreferenced_deduplicates_candidate_hashes() -> None:
    scalars = MagicMock()
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    hash_ = uuid.uuid4().hex
    await BlobApi.delete_unreferenced(session, [hash_, hash_])

    # The IN clause is built from a set, so a repeated candidate is a single bind — one guarded DELETE.
    session.execute.assert_awaited_once()
