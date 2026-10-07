"""EXECUTES the rebuild_index job's DB contract against a real Postgres (migration f7c2d9a4b1e5):

  * a job with ``document_id`` NULL (the collection-level rebuild) is accepted and round-trips;
  * the partial UNIQUE index ``uq_job_active_rebuild_per_collection`` refuses a second LIVE rebuild for
    the same collection, but not once the first is terminal, and never touches another collection;
  * ``IndexRebuildFacade.admit`` maps a live rebuild to IndexRebuildActiveError and live ingest jobs to
    CollectionBusyError, and ``RebuildGuard`` refuses an ingest admission while a rebuild is live.

Only a real DB evaluates a partial-index predicate — a shape-only unit test cannot prove it.
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import (
    CollectionBusyError,
    IndexRebuildActiveError,
    RebuildGuard,
)
from shared_libs.services.db.facades.index_rebuild_facade import IndexRebuildFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis.job_api import JobApi
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentStatus,
    Job,
    JobKind,
    JobStatus,
    SourceKind,
    WorkerHeartbeat,
)

pytestmark = pytest.mark.db


@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine + session per test against the head-migrated throwaway db."""
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            yield db_session
    finally:
        await engine.dispose()


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    """The facade-level Postgres client against the same throwaway db."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _seed_collection(db_session: AsyncSession) -> uuid.UUID:
    """Seed one throwaway collection; return its id."""
    collection = Collection(
        name=f"rebuild-{uuid.uuid4().hex[:8]}",
        supported_formats=["md"],
        max_file_size_bytes=10_000_000,
    )
    db_session.add(collection)
    await db_session.flush()
    return collection.id


async def _seed_document(db_session: AsyncSession, collection_id: uuid.UUID) -> uuid.UUID:
    """Seed one document in the collection; return its id."""
    document = Document(
        collection_id=collection_id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename="doc.md",
        format="md",
        mime_type="text/markdown",
        file_size=10,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.PENDING,
        pipeline_version="v1",
    )
    db_session.add(document)
    await db_session.flush()
    return document.id


async def _add_rebuild(
    db_session: AsyncSession, collection_id: uuid.UUID, status: JobStatus
) -> uuid.UUID:
    """Insert a document-less rebuild_index job at ``status``; return its id (flushed)."""
    job = Job(
        document_id=None, collection_id=collection_id, kind=JobKind.REBUILD_INDEX, status=status
    )
    db_session.add(job)
    await db_session.flush()
    return job.id


async def test_document_less_job_round_trips(session: AsyncSession) -> None:
    collection_id = await _seed_collection(session)
    job_id = await _add_rebuild(session, collection_id, JobStatus.PENDING)
    await session.commit()
    session.expire_all()

    job = await session.get(Job, job_id)

    assert job is not None
    assert job.document_id is None
    assert job.kind is JobKind.REBUILD_INDEX
    assert job.collection_id == collection_id


@pytest.mark.parametrize("second_status", [JobStatus.PENDING, JobStatus.RUNNING])
async def test_second_live_rebuild_is_refused(session: AsyncSession, second_status) -> None:
    collection_id = await _seed_collection(session)
    await _add_rebuild(session, collection_id, JobStatus.RUNNING)

    with pytest.raises(IntegrityError) as excinfo:
        await _add_rebuild(session, collection_id, second_status)

    assert "uq_job_active_rebuild_per_collection" in str(excinfo.value.orig)
    await session.rollback()


async def test_terminal_rebuild_and_other_collection_are_admitted(session: AsyncSession) -> None:
    collection_id = await _seed_collection(session)
    other_id = await _seed_collection(session)
    await _add_rebuild(session, collection_id, JobStatus.DONE)

    # Neither a fresh rebuild after a terminal one nor one on another collection violates the index.
    await _add_rebuild(session, collection_id, JobStatus.PENDING)
    await _add_rebuild(session, other_id, JobStatus.PENDING)


async def test_admit_refuses_a_second_rebuild(client: PostgresClient) -> None:
    async with client.session() as seed:
        collection_id = await _seed_collection(seed)
    facade = IndexRebuildFacade(client, qdrant=None, index_state=None)

    first = await facade.admit(collection_id)
    with pytest.raises(IndexRebuildActiveError) as excinfo:
        await facade.admit(collection_id)

    assert excinfo.value.job_id == first


async def test_admit_refuses_a_busy_collection(client: PostgresClient) -> None:
    async with client.session() as seed:
        collection_id = await _seed_collection(seed)
        document_id = await _seed_document(seed, collection_id)
        ingest = Job(document_id=document_id, collection_id=collection_id, status=JobStatus.RUNNING)
        seed.add(ingest)
        await seed.flush()
        ingest_id = ingest.id
    facade = IndexRebuildFacade(client, qdrant=None, index_state=None)

    with pytest.raises(CollectionBusyError) as excinfo:
        await facade.admit(collection_id)

    assert excinfo.value.job_ids == [ingest_id]


async def test_admit_unknown_collection_is_a_lookup_error(client: PostgresClient) -> None:
    facade = IndexRebuildFacade(client, qdrant=None, index_state=None)

    with pytest.raises(LookupError):
        await facade.admit(uuid.uuid4())


async def test_ingest_guard_refuses_while_a_rebuild_is_live(client: PostgresClient) -> None:
    async with client.session() as seed:
        collection_id = await _seed_collection(seed)
    await IndexRebuildFacade(client, qdrant=None, index_state=None).admit(collection_id)

    async with client.session() as ingest_session:
        with pytest.raises(IndexRebuildActiveError):
            await RebuildGuard.assert_no_rebuild(ingest_session, collection_id)


async def test_watchdog_gives_a_rebuild_its_own_budget(session: AsyncSession) -> None:
    """A rebuild copies the WHOLE collection: an hour-old rebuild on a live worker is within its own
    budget and is never reaped at the ingest timeout (that would lift its guards mid-copy), while an
    ingest job of the same age is past its timeout and IS listed."""
    now = datetime.now(UTC)
    worker_id = f"w-{uuid.uuid4().hex[:8]}"
    session.add(WorkerHeartbeat(worker_id=worker_id, last_seen=now, started_at=now))
    collection_id = await _seed_collection(session)
    document_id = await _seed_document(session, collection_id)
    hour_ago = now - timedelta(hours=1)
    rebuild = Job(
        document_id=None,
        collection_id=collection_id,
        kind=JobKind.REBUILD_INDEX,
        status=JobStatus.RUNNING,
        worker_id=worker_id,
        started_at=hour_ago,
    )
    ingest = Job(
        document_id=document_id,
        collection_id=collection_id,
        kind=JobKind.INGEST,
        status=JobStatus.RUNNING,
        worker_id=worker_id,
        started_at=hour_ago,
    )
    session.add_all([rebuild, ingest])
    await session.flush()

    listed = await JobApi.list_over_job_timeout(
        session, 1800.0, 300.0, 180.0, rebuild_job_timeout_seconds=7200.0
    )

    ids = {job.id for job, _ in listed}
    assert ingest.id in ids
    assert rebuild.id not in ids
    await session.rollback()
