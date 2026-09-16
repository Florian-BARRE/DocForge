"""EXECUTES the per-document active-job invariant against a real Postgres — the concurrency fix this
session shipped: at most ONE active (pending/running) ingestion job may exist per document, enforced by
the partial UNIQUE index ``uq_job_active_per_document`` (migration a1f4c9e7b2d3). A shape-only unit test
can never prove a partial-index predicate; only a real DB evaluates ``WHERE status IN
('pending','running')`` and raises the violation.

Covered, end to end:
  * A second live (pending/running) job for the SAME document is REFUSED by the DB — the INSERT raises,
    and ``IngestionFacade._is_active_job_conflict`` recognises it (so the enqueue paths resolve it to
    the existing active job instead of a 500).
  * A TERMINAL job leaves the active set — once the first job is DONE/FAILED/CANCELLED a fresh live job
    for the same document is admitted, so finishing a run frees the document for re-ingest.
  * ``IngestionFacade.reingest`` refuses a document that already has a live job (ALREADY_ACTIVE, pointing
    at the incumbent) and mints NO second row; on an idle document it admits a fresh job (exactly one
    active row).

Each test opens its own engine/session against the session-scoped migrated throwaway db and seeds its
own collection/document/job, so the tests are order-independent (every read is id-scoped).
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import ReingestOutcome
from shared_libs.services.db.facades.ingestion_facade import IngestionFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentStatus,
    Job,
    JobStatus,
    SourceKind,
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


async def _seed_document(db_session: AsyncSession) -> uuid.UUID:
    """Seed one collection + document (no job); return the document id."""
    # 1. A throwaway collection (unique name so parallel runs never collide).
    collection = Collection(
        name=f"active-job-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
    )
    db_session.add(collection)
    await db_session.flush()

    # 2. Its document, ready for ingestion.
    document = Document(
        collection_id=collection.id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename="doc.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.PENDING,
        pipeline_version="v1",
    )
    db_session.add(document)
    await db_session.flush()
    return document.id


async def _add_job(
    db_session: AsyncSession, document_id: uuid.UUID, status: JobStatus
) -> uuid.UUID:
    """Insert a job at the given status for the document; return its id (flushed)."""
    result = await db_session.execute(
        select(Document.collection_id).where(Document.id == document_id)
    )
    collection_id = result.scalar_one()
    job = Job(document_id=document_id, collection_id=collection_id, status=status)
    db_session.add(job)
    await db_session.flush()
    return job.id


async def _active_job_count(db_session: AsyncSession, document_id: uuid.UUID) -> int:
    """Count the document's live (pending/running) jobs, read straight from the DB."""
    db_session.expire_all()
    result = await db_session.execute(
        select(func.count(Job.id)).where(
            Job.document_id == document_id,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
    )
    return int(result.scalar_one())


# ── the DB invariant ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("second_status", [JobStatus.PENDING, JobStatus.RUNNING])
async def test_second_active_job_is_refused_by_the_partial_unique_index(
    session: AsyncSession, second_status: JobStatus
) -> None:
    """A second live job for the same document violates uq_job_active_per_document — whether the second
    is PENDING or RUNNING (both are inside the index predicate). The raised error is recognised as the
    active-job conflict, so the enqueue paths resolve it rather than surfacing a 500."""
    document_id = await _seed_document(session)
    await _add_job(session, document_id, JobStatus.RUNNING)

    with pytest.raises(IntegrityError) as excinfo:
        await _add_job(session, document_id, second_status)

    assert IngestionFacade._is_active_job_conflict(excinfo.value) is True
    await session.rollback()


async def test_a_terminal_job_frees_the_document_for_a_fresh_run(session: AsyncSession) -> None:
    """A DONE (terminal) job is OUTSIDE the partial index predicate, so a fresh live job for the same
    document is admitted — finishing a run frees the document for re-ingest."""
    document_id = await _seed_document(session)
    first = await _add_job(session, document_id, JobStatus.RUNNING)

    # Finish the first run — it leaves the active set.
    await JobApi.mark_done(session, first, finished_at=datetime.now(UTC))
    await session.flush()

    # A fresh live job is now allowed (no violation) — exactly one active row.
    await _add_job(session, document_id, JobStatus.PENDING)

    assert await _active_job_count(session, document_id) == 1


# ── the facade admission on top of the invariant ──────────────────────────────────────────────────────


async def test_reingest_refuses_a_document_with_an_active_job(migrated_db_dsn: str) -> None:
    """IngestionFacade.reingest returns ALREADY_ACTIVE (pointing at the incumbent) and mints NO second
    row when a live job already exists — the admission never violates the invariant."""
    client = PostgresClient(migrated_db_dsn)
    try:
        # Seed a document with one live job.
        async with client.session() as seed_session:
            document_id = await _seed_document(seed_session)
            active_id = await _add_job(seed_session, document_id, JobStatus.RUNNING)

        facade = IngestionFacade(client, qdrant=None, s3=None)
        result = await facade.reingest(document_id)

        assert result.outcome is ReingestOutcome.ALREADY_ACTIVE
        assert result.active_job_id == active_id
        async with client.session() as check_session:
            assert await _active_job_count(check_session, document_id) == 1
    finally:
        await client.dispose()


async def test_reingest_mints_a_fresh_job_on_an_idle_document(migrated_db_dsn: str) -> None:
    """On an idle document (no live job) reingest admits a fresh run — exactly one active row after."""
    client = PostgresClient(migrated_db_dsn)
    try:
        async with client.session() as seed_session:
            document_id = await _seed_document(seed_session)

        facade = IngestionFacade(client, qdrant=None, s3=None)
        result = await facade.reingest(document_id)

        assert result.outcome is ReingestOutcome.ADMITTED
        assert result.job is not None
        async with client.session() as check_session:
            assert await _active_job_count(check_session, document_id) == 1
    finally:
        await client.dispose()
