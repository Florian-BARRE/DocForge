# ====== Code Summary ======
# IngestionAdmission — the admission half of the ingestion persistence path: the dedup lookup, the
# one-transaction admission of a new document (+ its job + declared metadata), and the re-enqueue of an
# existing document. It also owns the decoders that tell a lost admission race (the document UNIQUE
# guard, the per-document active-job index) apart from any other integrity failure. Internal
# collaborator of IngestionFacade; callers go through ``Database.ingestion``.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.public_models import TextSanitizer
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import DocumentApi, IRApi, JobApi
from shared_libs.services.db.postgresql.tables import (
    Document,
    DocumentMetadata,
    DocumentStatus,
    Job,
)
from shared_libs.services.db.s3 import S3Client

# ====== Local Project Imports ======
from ..payloads import AdmissionResult, ReingestOutcome, ReingestResult
from ..rebuild_guard import RebuildGuard
from ..trace_purge import TracePurgeHelper

# The document UNIQUE constraint a concurrent duplicate upload violates. Its name is stable via the
# schema naming convention (uq_<table>_<first-column>) → ``UniqueConstraint(collection_id, source_hash,
# pipeline_version)`` on ``document``. asyncpg exposes the violated constraint name on its native
# error, which under SQLAlchemy's adapter is the wrapper's ``__cause__`` (``error.orig`` itself carries
# none), so both hops are inspected. Matching the name tells a lost admission race apart from any other
# integrity failure (which must still surface as a real error).
_DOCUMENT_UNIQUE_CONSTRAINT = "uq_document_collection_id"

# The partial UNIQUE index a concurrent SECOND active job for one document violates: at most one job
# may be PENDING/RUNNING per document (see ``job`` model / migration a1f4c9e7b2d3). On a unique-INDEX
# violation Postgres reports the INDEX name, which asyncpg surfaces as ``constraint_name`` (the same
# inspection hops as ``_DOCUMENT_UNIQUE_CONSTRAINT``). Matching it tells "a run is already in flight"
# apart from any other integrity failure (which must still surface as a real error).
_ACTIVE_JOB_UNIQUE_INDEX = "uq_job_active_per_document"


class IngestionAdmission(LoggerClass):
    """Admit a document + job, re-enqueue an existing one, and look up an already-ingested one."""

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

    @staticmethod
    def _is_duplicate_document(error: IntegrityError) -> bool:
        """
        Decide whether an IntegrityError is the document UNIQUE-guard violation (a lost admission race).

        Args:
            error (IntegrityError): The error raised by the admission INSERT's flush.

        Returns:
            bool: True only when the violated constraint is ``uq_document_collection_id``.
        """
        # 1. Walk the driver error and its __cause__ (the asyncpg native error carrying constraint_name)
        #    and match the document guard's name — precise, so an unrelated integrity failure is never
        #    treated as a benign duplicate.
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == _DOCUMENT_UNIQUE_CONSTRAINT
            for candidate in candidates
        )

    @staticmethod
    def _is_active_job_conflict(error: IntegrityError) -> bool:
        """
        Decide whether an IntegrityError is the per-document active-job guard violation (a lost race).

        Args:
            error (IntegrityError): The error raised by the job INSERT's flush.

        Returns:
            bool: True only when the violated index is ``uq_job_active_per_document``.
        """
        # 1. Walk the driver error and its __cause__ (the asyncpg native error carrying constraint_name)
        #    and match the active-job index's name — precise, so an unrelated integrity failure is never
        #    mistaken for a benign "already running" outcome.
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == _ACTIVE_JOB_UNIQUE_INDEX
            for candidate in candidates
        )

    async def find_duplicate(
        self, collection_id: uuid.UUID, source_hash: str, pipeline_version: str
    ) -> Document | None:
        """Dedup lookup — the already-ingested document for this exact content+config, or None."""
        async with self._postgres.session() as session:
            return await DocumentApi.find(session, collection_id, source_hash, pipeline_version)

    async def admit(
        self,
        document: Document,
        job: Job,
        declared_metadata: Sequence[DocumentMetadata] = (),
    ) -> AdmissionResult:
        """
        Register the document (PENDING), its ingestion job and its DECLARED metadata — one tx.

        The declared (user-origin) metadata is part of the admission: the worker reads it back
        to rebuild the pipeline's run input, so a half-admitted document must never exist.

        CONCURRENCY: two uploads of the same (collection, source_hash, pipeline_version) can both pass
        the router's dedup pre-check, then race here — the loser violates the document UNIQUE
        constraint. That is caught and resolved idempotently to the already-admitted document (no job),
        so a client retry never sees a 500. Any OTHER integrity failure is re-raised as a real error.

        Args:
            document (Document): The document row to create (status PENDING).
            job (Job): The ingestion job row (document/collection ids filled here).
            declared_metadata (Sequence[DocumentMetadata]): User-declared field rows
                (document_id filled here).

        Returns:
            AdmissionResult: ``created=True`` + the fresh document/job when this call won the insert;
                ``created=False`` + the incumbent document (no job) on a lost duplicate race.
        """
        # 1. Capture the dedup identity BEFORE the insert — after a failed flush + rollback the ORM
        #    object's attributes may be expired, so the incumbent re-query reads plain locals.
        collection_id = document.collection_id
        source_hash = document.source_hash
        pipeline_version = document.pipeline_version
        # 1b. NUL guard on the USER-origin text bound for Postgres: the uploaded filename and the
        #     user-declared metadata values can carry a U+0000 (a corrupt upload) that Postgres rejects
        #     for a text/jsonb column. GENERATED metadata is stripped by the translator; this closes the
        #     user-origin asymmetry. title/language are NULL at admit (set later by the translator).
        document.filename = TextSanitizer.strip_nul(document.filename)
        for row in declared_metadata:
            row.value = TextSanitizer.strip_nul(row.value)
        async with self._postgres.session() as session:
            # 1c. Refuse while the collection's index is being rebuilt (share-locks the collection row;
            #     raises IndexRebuildActiveError — the router maps it to 409).
            await RebuildGuard.assert_no_rebuild(session, collection_id)
            # 2. Insert the document; a UNIQUE violation is a concurrent duplicate admission.
            try:
                created = await DocumentApi.create(session, document)
            except IntegrityError as error:
                # 3. Re-raise anything that is NOT our duplicate guard — a real, unexpected failure.
                if not self._is_duplicate_document(error):
                    raise
                # 4. Lost the race: reset the aborted transaction, then return the incumbent document.
                await session.rollback()
                existing = await DocumentApi.find(
                    session, collection_id, source_hash, pipeline_version
                )
                return AdmissionResult(created=False, document=existing)
            # 5. Won the insert — mint the job and persist the declared metadata in the same tx. The
            #    per-document active-job index (uq_job_active_per_document) cannot fire here: the job is
            #    minted only for a DOCUMENT this tx just created (still uncommitted, so no other tx can
            #    see it to mint a competing job), so this path needs no active-job conflict handler. A
            #    re-upload mapping to an EXISTING busy document is handled above — it loses the document
            #    UNIQUE race and returns the incumbent with no job (never a second run).
            job.document_id = created.id
            job.collection_id = created.collection_id
            created_job = await JobApi.create(session, job)
            if declared_metadata:
                for row in declared_metadata:
                    row.document_id = created.id
                await DocumentApi.replace_metadata(session, created.id, list(declared_metadata))
        return AdmissionResult(created=True, document=created, job=created_job)

    async def reingest(
        self, document_id: uuid.UUID, replay_from: str | None = None
    ) -> ReingestResult:
        """
        Re-enqueue ingestion for an EXISTING document — no re-upload needed.

        The original bytes are content-addressed (``source_hash``) and the worker refetches them,
        the collection's CURRENT pipeline is read at run time, and a run is idempotent (the previous
        chunks/IR/pages are purged in ``save`` and ``index`` upserts the fresh points in place then purges
        the previous run's leftover points — a REPLACE, never an accumulation). So
        re-processing a document — e.g. after a pipeline or engine change — is just a fresh job on
        the same document, reset to PENDING. The USER-declared metadata rows survive (never touched
        here).

        CONCURRENCY GUARD: a document that already has a live (PENDING/RUNNING) job is REFUSED
        (``ALREADY_ACTIVE``) rather than given a second job — two parallel runs of one document
        interleave their Qdrant upsert + stale-point purge and strand the loser's points as live
        orphans. Two layers enforce this: (1) the document row is locked ``FOR UPDATE`` for the
        admission so two concurrent reingests serialise — the second blocks, then sees the first's
        fresh PENDING job and refuses at the pre-check; (2) the DB invariant
        ``uq_job_active_per_document`` (a partial UNIQUE index over the live rows) is the hard,
        cross-container backstop — should the job INSERT still race a concurrent live job (a path that
        does not take the document lock), the flush raises and is resolved here to ``ALREADY_ACTIVE``
        pointing at the winning job, never a 500 and never a second active row.

        REPLAY: ``replay_from`` (a post-IR stage key, already validated against the pipeline by the
        caller) is stamped on the job row — the worker reads it there and re-runs only that stage and
        its downstream from the persisted IR. It requires a persisted IR (checked under the same lock), and
        it keeps a DONE/FAILED document's status (not reset to PENDING): the prior content stays served
        until the replay commits, and a failed replay leaves the status as it was.

        Args:
            document_id (uuid.UUID): The document to re-ingest.
            replay_from (str | None): Replay from this stage instead of a full run (None = full run).

        Returns:
            ReingestResult: ADMITTED (+ document + fresh job) when a run was minted; NOT_FOUND for an
                unknown id; ALREADY_ACTIVE (+ the blocking job id) when a run is already in flight;
                NOT_REPLAYABLE when a replay was asked but no IR is persisted.
        """
        async with self._postgres.session() as session:
            # 1. Lock the row so a concurrent reingest of the same document can't also pass step 2.
            document = await DocumentApi.get_for_update(session, document_id)
            if document is None:
                return ReingestResult(outcome=ReingestOutcome.NOT_FOUND)
            # 1b. Refuse while the collection's index is being rebuilt (IndexRebuildActiveError → 409).
            await RebuildGuard.assert_no_rebuild(session, document.collection_id)
            # 2. Refuse a duplicate run while one is already queued or executing.
            active = await JobApi.get_active_for_document(session, document_id)
            if active is not None:
                return ReingestResult(
                    outcome=ReingestOutcome.ALREADY_ACTIVE, active_job_id=active.id
                )
            # 2b. A replay stands on the persisted IR — refuse it when there is none.
            if replay_from is not None and not await IRApi.has_blocks(session, document_id):
                return ReingestResult(outcome=ReingestOutcome.NOT_REPLAYABLE)
            # 3. Capture the document's PRIOR job ids (before minting the fresh one) — the run being
            #    replaced; their full-trace payloads are reclaimed after the commit.
            prior_job_ids = await JobApi.list_job_ids_for_document(session, document_id)
            # 4. Mint the fresh job and reset the document to PENDING (one transaction). The INSERT is
            #    the race-safe admission: on the per-document active-job index violation the whole tx
            #    is rolled back and resolved to the winning live job (ALREADY_ACTIVE), so a run that
            #    slipped past the pre-check never mints a second active row.
            job = Job(
                document_id=document.id,
                collection_id=document.collection_id,
                replay_from=replay_from,
            )
            try:
                created_job = await JobApi.create(session, job)
            except IntegrityError as error:
                if not self._is_active_job_conflict(error):
                    raise
                await session.rollback()
                existing = await JobApi.get_active_for_document(session, document_id)
                return ReingestResult(
                    outcome=ReingestOutcome.ALREADY_ACTIVE,
                    active_job_id=existing.id if existing is not None else None,
                )
            # A replay keeps a DONE/FAILED document's status: its persisted chunks/points stay served
            # until the replay commits, and a failed replay must leave that status as it was.
            if replay_from is None or document.status not in (
                DocumentStatus.DONE,
                DocumentStatus.FAILED,
            ):
                await DocumentApi.set_status(session, document_id, DocumentStatus.PENDING)
        # 5. Reclaim the superseded runs' full-trace payloads (best-effort — the old job rows survive
        #    a reingest, so this also clears their now-dangling refs; a failure never blocks the run).
        await TracePurgeHelper.purge(self._postgres, self._s3, prior_job_ids)
        return ReingestResult(outcome=ReingestOutcome.ADMITTED, document=document, job=created_job)


__all__ = ["IngestionAdmission"]
