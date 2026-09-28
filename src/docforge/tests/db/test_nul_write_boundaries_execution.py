"""EXECUTES two of the remaining NUL (U+0000) write boundaries against a REAL Postgres — the audit
follow-up to the ingestion-path fix already guarded by ``test_nul_jsonb_persistence``. Each of these
paths writes external/document/LLM text to a Postgres text/jsonb column and, before the fix, could
crash with asyncpg's ``UntranslatableCharacterError`` on a stray NUL:

  * admission / upload — ``IngestionFacade.admit`` strips the USER-origin filename and declared
    metadata values (the GENERATED metadata was already covered by the translator).
  * the failure double-fault — ``JobApi.mark_failed`` / ``mark_terminal`` strip the error/reason so
    marking a job FAILED (whose error message may echo raw document bytes) never itself raises.

The third boundary — collection-transfer import (``RowDeserializer``) — is guarded serviceless in
``tests/units/transfer/`` (its conftest imports ``collection_transfer`` cleanly, whereas importing it
by the ``worker.backend.libs`` path here drags the whole worker app in); Postgres' actual NUL rejection
is already proven by ``test_nul_jsonb_persistence``.

Only a real DB proves the fix: the whole defect is that Postgres — not the ORM — rejects the NUL, so a
mock can never reproduce it. The NUL is built with ``chr(0)`` so this source file never contains a raw
null byte (Python could not parse one).
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import IngestionFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentMetadata,
    DocumentStatus,
    Job,
    JobStatus,
    MetadataField,
    SourceKind,
)

pytestmark = pytest.mark.db

_NUL = chr(0)


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
    """A PostgresClient bound to the throwaway db, for facade calls that open their own session."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _seed_collection(db_session: AsyncSession) -> uuid.UUID:
    """Create a throwaway collection (unique name so parallel runs never collide); return its id."""
    collection = Collection(
        name=f"nul-boundary-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
    )
    db_session.add(collection)
    await db_session.flush()
    return collection.id


# ── admission / upload — admit strips the USER-origin filename + declared metadata values ────────────


async def test_admit_strips_nul_from_filename_and_user_metadata(
    session: AsyncSession, client: PostgresClient
) -> None:
    """``admit`` with a filename and a USER metadata value carrying a U+0000 persists cleanly: the
    document row and its declared metadata store NUL-free (the user-origin half of the translator net)."""
    # 1. A collection + a USER-origin document-scope field the declared metadata points at.
    collection_id = await _seed_collection(session)
    field = MetadataField(
        collection_id=collection_id,
        field_name="author",
        field_type=FieldType.TEXT,
        required=False,
        origin=FieldOrigin.USER,
        scope=FieldScope.DOCUMENT,
    )
    session.add(field)
    await session.flush()
    field_id = field.id
    await session.commit()

    # 2. The admission inputs, both carrying a NUL in their external text.
    document = Document(
        collection_id=collection_id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename=f"con{_NUL}tract.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.PENDING,
        pipeline_version="v1",
    )
    declared = DocumentMetadata(
        field_id=field_id,
        value=f"Jane{_NUL} Doe",
        origin=FieldOrigin.USER,
    )

    # 3. Admit through the real facade (opens its own transaction) — must not raise.
    facade = IngestionFacade(client, qdrant=None, s3=None)
    result = await facade.admit(document, Job(), declared_metadata=[declared])
    assert result.created is True

    # 4. Read the committed rows back: both stored NUL-free.
    session.expire_all()
    stored_doc = await session.scalar(select(Document).where(Document.id == result.document.id))
    assert stored_doc.filename == "contract.pdf"
    stored_value = await session.scalar(
        select(DocumentMetadata.value).where(DocumentMetadata.document_id == result.document.id)
    )
    assert stored_value == "Jane Doe"


# ── the failure double-fault — mark_failed / mark_terminal strip the error before the terminal write ─


async def _seed_running_job(db_session: AsyncSession) -> uuid.UUID:
    """Seed a collection + document + RUNNING job; return the job id."""
    collection_id = await _seed_collection(db_session)
    document = Document(
        collection_id=collection_id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename="doc.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.PROCESSING,
        pipeline_version="v1",
    )
    db_session.add(document)
    await db_session.flush()
    job = Job(
        document_id=document.id,
        collection_id=collection_id,
        status=JobStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.flush()
    return job.id


async def test_mark_failed_with_nul_error_does_not_double_fault(session: AsyncSession) -> None:
    """Failing a job whose error string echoes a raw NUL (a parser exception over corrupt bytes) must
    succeed — the terminal write strips U+0000 so it never raises a SECOND UntranslatableCharacterError."""
    job_id = await _seed_running_job(session)

    await JobApi.mark_failed(
        session,
        job_id,
        error=f"parse failed: byte{_NUL} stream",
        finished_at=datetime.now(UTC),
        error_type=f"Value{_NUL}Error",
    )

    session.expire_all()
    row = await session.scalar(select(Job).where(Job.id == job_id))
    assert row.status == JobStatus.FAILED
    assert row.error == "parse failed: byte stream"
    assert row.error_type == "ValueError"


async def test_mark_terminal_with_nul_reason_does_not_double_fault(session: AsyncSession) -> None:
    """The shared force-terminate/reaper path: terminating a job with a reason carrying a NUL succeeds
    and stores the reason NUL-free — a job can always be reaped, even over a NUL-bearing error."""
    job_id = await _seed_running_job(session)

    returned = await JobApi.mark_terminal(
        session,
        job_id,
        status=JobStatus.FAILED,
        reason=f"reaped: worker{_NUL} killed",
        finished_at=datetime.now(UTC),
        error_type=f"worker{_NUL}_killed",
    )

    assert returned is not None
    session.expire_all()
    row = await session.scalar(select(Job).where(Job.id == job_id))
    assert row.status == JobStatus.FAILED
    assert row.error == "reaped: worker killed"
    assert row.error_type == "worker_killed"
