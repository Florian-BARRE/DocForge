"""EXECUTES the artifact-cache data layer (ArtifactCacheApi + ArtifactCacheFacade) against a real
Postgres, with an in-memory fake S3 for the byte side. Covers: the upsert-on-hit (hit_count +
last_hit_at bump), the idempotent store insert (on_conflict_do_nothing), the GC read paths
(list_expired / collection_sizes / list_by_recency), on-document-delete row drops, the facade
store→lookup→load round-trip, and the GC prune (TTL + per-collection LRU size cap) with the global
ref-count orphan sweep that reclaims a stage-artifact blob once its last pointer is gone.

Each test opens its own engine/session against the session-scoped migrated throwaway db; the
artifact_cache + blob tables are emptied at the top of each test so the suite is order-independent.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared_libs.services.db.facades import ArtifactCacheFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ArtifactCacheApi
from shared_libs.services.db.postgresql.tables import ArtifactCache, ArtifactType, Blob, BlobKind

pytestmark = pytest.mark.db

_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_COLL_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_COLL_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


# ── in-memory fake S3 (satisfies the real S3ObjectApi) ───────────────────────────────────────────
class _FakeRawS3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    async def put_object(self, Bucket, Key, Body, ContentType="application/octet-stream") -> None:
        self._objects[Key] = Body

    async def delete_objects(self, Bucket, Delete) -> None:
        for entry in Delete["Objects"]:
            self._objects.pop(entry["Key"], None)

    async def get_object(self, Bucket, Key):
        data = self._objects[Key]

        class _Body:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def read(self_inner):
                return data

        return {"Body": _Body()}


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket = "test-bucket"

    @asynccontextmanager
    async def client(self):
        yield _FakeRawS3(self.objects)


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            await db_session.execute(delete(ArtifactCache))
            await db_session.execute(delete(Blob).where(Blob.kind == BlobKind.STAGE_ARTIFACT))
            await db_session.commit()
            yield db_session
    finally:
        await engine.dispose()


@pytest.fixture
async def client(migrated_db_dsn: str, session: AsyncSession) -> AsyncIterator[PostgresClient]:
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


def _row(cache_key: str, *, collection=_COLL_A, content_hash=None, size=100, document=None):
    return ArtifactCache(
        cache_key=cache_key,
        content_hash=content_hash or (cache_key[:1] * 64),
        stage_key="parser/docling/1",
        artifact_type=ArtifactType.PARSE_IR,
        engine_version="1.1",
        document_id=document,
        collection_id=collection,
        size_bytes=size,
    )


# ── ArtifactCacheApi (raw table ops) ─────────────────────────────────────────────────────────────
async def test_insert_get_and_record_hit(session: AsyncSession) -> None:
    await ArtifactCacheApi.insert(session, _row("k1"))
    await session.commit()

    fetched = await ArtifactCacheApi.get(session, "k1")
    assert fetched is not None and fetched.hit_count == 0 and fetched.last_hit_at is None

    await ArtifactCacheApi.record_hit(session, "k1", _NOW)
    await session.commit()
    session.expire_all()
    bumped = await ArtifactCacheApi.get(session, "k1")
    assert bumped.hit_count == 1 and bumped.last_hit_at is not None


async def test_insert_is_idempotent_on_conflict(session: AsyncSession) -> None:
    await ArtifactCacheApi.insert(session, _row("k1", size=100))
    await ArtifactCacheApi.insert(session, _row("k1", size=999))  # same key → no-op
    await session.commit()

    kept = await ArtifactCacheApi.get(session, "k1")
    assert kept.size_bytes == 100  # the first insert stands


async def test_list_expired_uses_coalesce_last_hit_then_created(session: AsyncSession) -> None:
    fresh = _row("fresh")
    fresh.created_at = _NOW
    fresh.last_hit_at = _NOW
    stale = _row("stale")
    stale.created_at = _NOW - timedelta(days=90)
    stale.last_hit_at = None  # falls back to created_at → stale
    session.add_all([fresh, stale])
    await session.commit()

    expired = await ArtifactCacheApi.list_expired(session, _NOW - timedelta(days=30))
    assert {row.cache_key for row in expired} == {"stale"}


async def test_collection_sizes_and_delete_for_documents(session: AsyncSession) -> None:
    doc = uuid.uuid4()
    session.add_all(
        [
            _row("a", collection=_COLL_A, size=100, document=doc),
            _row("b", collection=_COLL_A, size=250),
            _row("c", collection=_COLL_B, size=50),
        ]
    )
    await session.commit()

    sizes = dict(await ArtifactCacheApi.collection_sizes(session))
    assert sizes == {_COLL_A: 350, _COLL_B: 50}

    await ArtifactCacheApi.delete_for_documents(session, [doc])
    await session.commit()
    assert await ArtifactCacheApi.get(session, "a") is None
    assert await ArtifactCacheApi.get(session, "b") is not None


# ── ArtifactCacheFacade (store + GC over real PG + fake S3) ──────────────────────────────────────
async def test_facade_store_lookup_and_load_round_trip(client: PostgresClient) -> None:
    s3 = _FakeS3Client()
    facade = ArtifactCacheFacade(client, s3)
    row = _row("k1", content_hash="c" * 64, size=5)

    await facade.store(row, b"hello")

    assert (await facade.lookup("k1")) is not None
    assert await facade.load_bytes("c" * 64) == b"hello"
    # A blob registry row was written under STAGE_ARTIFACT.
    async with client.session() as s:
        blob = await s.get(Blob, "c" * 64)
    assert blob is not None and blob.kind == BlobKind.STAGE_ARTIFACT


async def test_prune_ttl_evicts_and_orphan_sweep_frees_the_blob(client: PostgresClient) -> None:
    s3 = _FakeS3Client()
    facade = ArtifactCacheFacade(client, s3)
    await facade.store(_row("k1", content_hash="c" * 64, size=5), b"hello")

    # store() stamps created_at at the real now (server default); sweeping from now+60d with a 30d TTL
    # puts the row's recency (created_at ≈ real now) well before the cutoff → stale, evicted, orphaned.
    summary = await facade.prune(datetime.now(UTC) + timedelta(days=60), timedelta(days=30), 0)

    assert summary.evicted_rows == 1 and summary.freed_blobs == 1
    assert (await facade.lookup("k1")) is None
    assert s3.objects == {}  # the S3 stage-artifact object was reclaimed
    async with client.session() as s:
        assert (await s.get(Blob, "c" * 64)) is None


async def test_prune_size_cap_evicts_least_recently_used_first(client: PostgresClient) -> None:
    s3 = _FakeS3Client()
    facade = ArtifactCacheFacade(client, s3)
    # Three 100-byte rows in one collection; distinct last_hit_at so LRU order is deterministic.
    async with client.session() as s:
        for name, age_days in (("old", 3), ("mid", 2), ("new", 1)):
            row = _row(name, content_hash=name.ljust(64, "0"), size=100)
            row.last_hit_at = _NOW - timedelta(days=age_days)
            s.add(row)
            s.add(
                Blob(
                    content_hash=name.ljust(64, "0"),
                    s3_key=name.ljust(64, "0"),
                    mime_type="application/x-msgpack",
                    size_bytes=100,
                    kind=BlobKind.STAGE_ARTIFACT,
                )
            )
        await s.commit()

    # Cap = 250 bytes, TTL disabled → keep the 2 freshest (new+mid=200), evict the oldest (old).
    summary = await facade.prune(_NOW, timedelta(0), 250)

    assert summary.evicted_rows == 1
    assert (await facade.lookup("old")) is None
    assert (await facade.lookup("mid")) is not None and (await facade.lookup("new")) is not None


async def test_drop_for_document_removes_rows_and_sweeps_its_orphan_blob(
    client: PostgresClient,
) -> None:
    s3 = _FakeS3Client()
    facade = ArtifactCacheFacade(client, s3)
    doc = uuid.uuid4()
    await facade.store(_row("k1", content_hash="c" * 64, size=5, document=doc), b"hi")

    removed = await facade.drop_for_document(doc)

    assert removed == 1
    assert (await facade.lookup("k1")) is None
    assert s3.objects == {}  # the orphaned blob was swept


async def test_prune_grace_window_protects_a_just_stored_orphan_blob(
    client: PostgresClient,
) -> None:
    """The orphan sweep must SKIP a stage-artifact blob younger than the grace window — a concurrent
    store() puts bytes + blob row BEFORE its pointer, so a grace-less sweep could reclaim it mid-flight
    (Finding 4b). Here the blob is registered but its pointer is deleted (looks orphan); a wide grace
    keeps it, a zero grace reclaims it."""
    s3 = _FakeS3Client()
    facade = ArtifactCacheFacade(client, s3)
    # Store, then drop only the POINTER so the freshly-created blob looks orphan (created_at ≈ now).
    await facade.store(_row("k1", content_hash="c" * 64, size=5), b"hi")
    async with client.session() as s:
        await s.execute(delete(ArtifactCache).where(ArtifactCache.cache_key == "k1"))
        await s.commit()

    # 1. A wide grace window (1 day) skips the just-created blob — TTL/cap disabled, sweep only.
    summary = await facade.prune(datetime.now(UTC), timedelta(0), 0, blob_grace=timedelta(days=1))
    assert summary.freed_blobs == 0
    assert s3.objects != {}  # the young orphan survived the grace-guarded sweep

    # 2. Zero grace (cutoff = now) reclaims the aged-out orphan on the next sweep.
    summary = await facade.prune(datetime.now(UTC), timedelta(0), 0, blob_grace=timedelta(0))
    assert summary.freed_blobs == 1
    assert s3.objects == {}
