"""EXECUTES the trace-payload footprint accounting against a real Postgres: the per-document SUM the
storage footprint reads, the write path that records a job's stored-trace byte total, and the
purge/clear convergence that zeroes it. A real DB is what proves the GROUP BY (including the
null-document fold), the ``COALESCE(SUM(...), 0)``, and the ``UPDATE ... SET trace_payload_bytes = 0``
in ``clear_trace_refs`` — a mock cannot catch an aggregate or a WHERE bug, which is exactly this
feature's defect class.

Covered, end to end:
  * trace_bytes_per_document returns one summed row per document (multiple jobs per document add up)
    AND a single null-document row folding every doc-less job (the collection-only bucket).
  * set_trace_payload_bytes writes the recorded total onto the job row.
  * clear_trace_refs (the purge/GC/reingest choke point) zeroes trace_payload_bytes so the footprint
    converges once the bytes are reclaimed.

Each test opens its own engine/session against the session-scoped migrated throwaway db and seeds its
own collection/documents/jobs, so the tests are order-independent (every read is id-scoped).
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis import JobApi, StorageFootprintApi
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


async def _seed_collection(db_session: AsyncSession) -> uuid.UUID:
    """Seed a throwaway collection (unique name so parallel runs never collide); return its id."""
    collection = Collection(
        name=f"trace-footprint-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
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
        filename="doc.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.DONE,
        pipeline_version="v1",
    )
    db_session.add(document)
    await db_session.flush()
    return document.id


async def _seed_job(
    db_session: AsyncSession,
    *,
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    trace_payload_bytes: int = 0,
    status: JobStatus = JobStatus.DONE,
) -> uuid.UUID:
    """Seed a job (terminal by default) carrying a recorded trace-payload byte total; return its id."""
    job = Job(
        document_id=document_id,
        collection_id=collection_id,
        status=status,
        trace_payload_bytes=trace_payload_bytes,
    )
    db_session.add(job)
    await db_session.flush()
    return job.id


async def _trace_bytes(db_session: AsyncSession, job_id: uuid.UUID) -> int:
    """Read the job's CURRENT committed trace_payload_bytes straight from the DB."""
    db_session.expire_all()
    return await db_session.scalar(select(Job.trace_payload_bytes).where(Job.id == job_id))


async def test_trace_bytes_per_document_sums_and_folds_null_document(session: AsyncSession) -> None:
    """Multiple jobs per document add up; every doc-less job folds into a single null-document row."""
    # 1. A collection with two documents, each with two jobs, plus a null-document job.
    collection_id = await _seed_collection(session)
    doc_a = await _seed_document(session, collection_id)
    doc_b = await _seed_document(session, collection_id)
    await _seed_job(
        session, collection_id=collection_id, document_id=doc_a, trace_payload_bytes=700
    )
    await _seed_job(session, collection_id=collection_id, document_id=doc_a, trace_payload_bytes=50)
    await _seed_job(
        session, collection_id=collection_id, document_id=doc_b, trace_payload_bytes=300
    )

    # 2. The real GROUP BY: DOC_A folds its two jobs (750), DOC_B one (300).
    rows = await StorageFootprintApi.trace_bytes_per_document(session, collection_id)
    by_doc = dict(rows)

    assert by_doc[doc_a] == 750
    assert by_doc[doc_b] == 300


async def test_trace_bytes_per_document_is_empty_when_nothing_stored(session: AsyncSession) -> None:
    """A collection whose jobs stored no trace (all zero) reports zeros, never a missing row error."""
    # 1. One document, one job that stored no full trace (the default 0).
    collection_id = await _seed_collection(session)
    doc = await _seed_document(session, collection_id)
    await _seed_job(session, collection_id=collection_id, document_id=doc, trace_payload_bytes=0)

    # 2. The row is present but zero — nothing to reclaim.
    rows = await StorageFootprintApi.trace_bytes_per_document(session, collection_id)
    assert dict(rows)[doc] == 0


async def test_set_trace_payload_bytes_records_the_total(session: AsyncSession) -> None:
    """The write path records the summed stored-trace bytes onto the job row."""
    collection_id = await _seed_collection(session)
    doc = await _seed_document(session, collection_id)
    job_id = await _seed_job(
        session, collection_id=collection_id, document_id=doc, trace_payload_bytes=0
    )

    await JobApi.set_trace_payload_bytes(session, job_id, 4096)

    assert await _trace_bytes(session, job_id) == 4096


async def test_clear_trace_refs_zeroes_the_footprint_counter(session: AsyncSession) -> None:
    """Purge/GC/reingest convergence: clearing a job's refs also zeroes trace_payload_bytes."""
    # 1. A job with a recorded trace footprint (as if payloads were stored).
    collection_id = await _seed_collection(session)
    doc = await _seed_document(session, collection_id)
    job_id = await _seed_job(
        session, collection_id=collection_id, document_id=doc, trace_payload_bytes=8192
    )

    # 2. The single purge choke point clears refs AND zeroes the counter in one transaction.
    await JobApi.clear_trace_refs(session, [job_id])

    assert await _trace_bytes(session, job_id) == 0


async def test_set_trace_payload_bytes_persists_a_value_beyond_the_integer_cap(
    session: AsyncSession,
) -> None:
    """A large fan-out job's summed trace bytes can exceed the ~2.1 GB Integer cap; BigInteger holds
    it exactly. This FAILS on the old Integer column (NumericValueOutOfRange on the UPDATE)."""
    # 1. Seed a job and record a byte total well past 2^31-1 (2 147 483 647).
    collection_id = await _seed_collection(session)
    doc = await _seed_document(session, collection_id)
    job_id = await _seed_job(session, collection_id=collection_id, document_id=doc)
    over_int_cap = 3_000_000_000

    await JobApi.set_trace_payload_bytes(session, job_id, over_int_cap)

    # 2. It round-trips exactly — proof the column is BigInteger, not the ~2.1 GB Integer.
    assert await _trace_bytes(session, job_id) == over_int_cap


async def test_terminal_job_id_gather_excludes_in_flight_jobs(session: AsyncSession) -> None:
    """The purge id-gather returns TERMINAL jobs only: a pending/running run mid trace-finalize is
    skipped so a purge never races it (or strands its bytes)."""
    # 1. One terminal (done + failed) document and one document with an in-flight (pending) job.
    collection_id = await _seed_collection(session)
    doc_terminal = await _seed_document(session, collection_id)
    doc_active = await _seed_document(session, collection_id)
    done_id = await _seed_job(
        session, collection_id=collection_id, document_id=doc_terminal, status=JobStatus.DONE
    )
    failed_id = await _seed_job(
        session, collection_id=collection_id, document_id=doc_terminal, status=JobStatus.FAILED
    )
    await _seed_job(
        session, collection_id=collection_id, document_id=doc_active, status=JobStatus.PENDING
    )

    # 2. Collection-scope: the two terminal jobs are gathered, the in-flight one is not.
    coll_ids = await JobApi.list_terminal_job_ids_for_collection(session, collection_id)
    assert set(coll_ids) == {done_id, failed_id}

    # 3. Document-scope: the terminal doc yields its terminal jobs; the in-flight doc yields none.
    assert set(await JobApi.list_terminal_job_ids_for_document(session, doc_terminal)) == {
        done_id,
        failed_id,
    }
    assert await JobApi.list_terminal_job_ids_for_document(session, doc_active) == []
