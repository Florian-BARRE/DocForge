# ====== Code Summary ======
# IngestionFacade — the worker's persistence path, in pipeline order: dedup lookup, admission
# (document + job), blob storage (S3 then registry), the ONE-TRANSACTION save of everything a pure
# pipeline run produced (facts + pages + metadata + IR + chunks — idempotent on re-ingest via the
# purge-then-insert pattern), and the vector indexing (ensure the Qdrant collection from the schema,
# upsert the fresh points, purge the document's leftover ones, flag the chunks indexed). Re-ingest is
# a REPLACE at every layer: Postgres purges-then-inserts, and Qdrant upserts the deterministic
# (document, ordinal) point ids in place, then drops the ids the new run no longer produced.

# ====== Standard Library Imports ======
import hashlib
import json
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.public_models import TextSanitizer
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    BlobApi,
    ChunkApi,
    CollectionApi,
    DocumentApi,
    IRApi,
    JobApi,
)
from shared_libs.services.db.postgresql.apis.execution_tree import (
    ExecutionTreeFlattener,
    TraceRefs,
)
from shared_libs.services.db.postgresql.tables import (
    Blob,
    Document,
    DocumentMetadata,
    DocumentStatus,
    Job,
)
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
    VectorNames,
)
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .payloads import AdmissionResult, IngestionPayload, ReingestOutcome, ReingestResult
from .rebuild_guard import RebuildGuard
from .trace_purge import TracePurgeHelper
from .undeclared_vector_error import UndeclaredVectorError

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


class IngestionFacade(LoggerClass):
    """The worker's persistence path — admit, store blobs, save the run, index the vectors."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
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

    async def store_blobs(self, objects: Sequence[S3Object], rows: Sequence[Blob]) -> None:
        """
        Store blob bytes in S3, then register them in Postgres.

        S3 first: if the registry write then fails, the orphan S3 objects are harmless; the
        reverse order would register rows whose bytes do not exist.
        """
        # 1. The bytes.
        if objects:
            async with self._s3.client() as s3:
                await S3ObjectApi.put_many(s3, self._s3.bucket, objects)
        # 2. The registry rows — one bulk insert (idempotent per content hash).
        async with self._postgres.session() as session:
            await BlobApi.register_many(session, rows)

    @staticmethod
    def __trace_object(payload: dict, key_prefix: str, max_payload_bytes: int) -> S3Object:
        """Serialise one full trace payload to a content-addressed S3 object (truncated over the cap).

        The key is ``{key_prefix}{sha256}`` (the prefix ends with ``/``) so an unchanged IR reused
        across hops content-addresses to the SAME object (stored once), and a later GC can
        prefix-delete the whole ``trace/{job_id}/`` space. A payload whose serialised form exceeds
        ``max_payload_bytes`` is replaced by a compact truncation marker (the row's shape summary
        already describes the true payload).
        """
        raw = json.dumps(payload, default=str).encode()
        if len(raw) > max_payload_bytes:
            marker = {
                "_truncated": True,
                "original_bytes": len(raw),
                "preview": raw[:max_payload_bytes].decode(errors="replace"),
            }
            raw = json.dumps(marker).encode()
        digest = hashlib.sha256(raw).hexdigest()
        return S3Object(key=f"{key_prefix}{digest}", data=raw, content_type="application/json")

    async def store_trace_payloads(
        self, job_id: uuid.UUID, record: NodeExecutionRecord, max_payload_bytes: int
    ) -> dict[str, TraceRefs]:
        """
        Store each node's FULL input/output payload in the object store (the full trace tier).

        Walks the execution tree, serialises every full payload the engine attached (it does so ONLY
        at ``TraceLevel.FULL``), content-addresses it under a job-prefixed key ``trace/{job_id}/{hash}``
        (an unchanged IR reused across hops is stored once; a later GC prefix-deletes the whole job),
        and returns the per-node-path references the tree-persist step stamps onto the rows.

        Best-effort by contract: a store failure is logged and dropped (that node simply keeps no
        ref / ``has_full`` false) — trace capture must NEVER fail an ingestion that already produced
        its bundle. A payload over ``max_payload_bytes`` is stored truncated behind a marker.

        Args:
            job_id (uuid.UUID): The job whose trace payloads are stored (its key prefix).
            record (NodeExecutionRecord): The run's outermost execution record.
            max_payload_bytes (int): Per-payload byte cap; a larger serialised payload is truncated.

        Returns:
            dict[str, TraceRefs]: Per node_path, the object-store keys of its stored input/output
                payloads (a side is absent when the node had no full payload or the store missed).
        """
        # 1. Collect every full payload the engine attached (full tier only), keyed by node_path/side.
        prefix = DatabaseHelpers.trace_prefix(job_id)
        pending: list[tuple[str, str, S3Object]] = []
        for node in ExecutionTreeFlattener.flatten(record):
            if node.record.resolved_input is not None:
                obj = self.__trace_object(node.record.resolved_input, prefix, max_payload_bytes)
                pending.append((node.node_path, "input", obj))
            if node.record.output is not None:
                obj = self.__trace_object(node.record.output, prefix, max_payload_bytes)
                pending.append((node.node_path, "output", obj))
        if not pending:
            return {}

        # 2. One S3 client scope AND one put_many for the whole batch — up to ~60 sequential PUTs
        #    collapsed into a single call (content-addressed keys make repeated puts idempotent).
        #    Best-effort by contract: a batch failure is logged and drops every ref for this run (the
        #    rows simply keep no full payload), never failing an ingestion that already produced its
        #    bundle.
        input_by_path: dict[str, str] = {}
        output_by_path: dict[str, str] = {}
        try:
            async with self._s3.client() as s3:
                await S3ObjectApi.put_many(s3, self._s3.bucket, [obj for _, _, obj in pending])
        except Exception as exc:
            self.logger.warning(
                f"Trace payload store failed for job {job_id}; dropping {len(pending)} ref(s): {exc}"
            )
            return {}
        # ACCEPTED LIMITATION (rare, no code change): the caller stamps these refs onto the rows via
        # ``persist_execution_tree`` AFTER this returns. If that tree-persist fails, the S3 bytes are
        # written but no row flags ``has_full_*`` — the retention GC (which keys off those flags) then
        # never reclaims them, so they can strand. Rare (persist runs right after) and still reclaimable
        # by an explicit collection/document purge (it prefix-deletes ``trace/{job_id}/`` by job id,
        # not by flag); a full fix would need a two-phase commit not worth its weight here.
        for node_path, side, obj in pending:
            (input_by_path if side == "input" else output_by_path)[node_path] = obj.key

        # 3. Record the stored footprint on the job row (best-effort): the content-addressed objects
        #    are deduped by key (a payload reused across hops is stored — and counted — once), so the
        #    total mirrors what the ``trace/{job_id}/`` prefix physically holds. A persist failure is
        #    swallowed — trace accounting must never fail an ingestion that already produced its bundle.
        total_bytes = sum({obj.key: len(obj.data) for _, _, obj in pending}.values())
        try:
            async with self._postgres.session() as session:
                await JobApi.set_trace_payload_bytes(session, job_id, total_bytes)
        except Exception as exc:
            self.logger.warning(f"Trace payload byte accounting failed for job {job_id}: {exc}")

        # 4. Fold the two sides into one TraceRefs per node_path.
        paths = set(input_by_path) | set(output_by_path)
        return {
            path: TraceRefs(input_ref=input_by_path.get(path), output_ref=output_by_path.get(path))
            for path in paths
        }

    async def save(
        self,
        document_id: uuid.UUID,
        payload: IngestionPayload,
        warning_reason: str | None = None,
    ) -> None:
        """
        Persist everything a pipeline run produced, in ONE transaction.

        Idempotent on re-ingest: the document's previous chunks and IR are purged first, then the
        fresh rows inserted, so re-running the same document never conflicts on primary keys.

        Re-ingest also PURGES superseded blobs. Postgres and Qdrant are REPLACED here, but blobs are
        content-addressed and only ever added (``store_blobs`` ran before this) — so a re-ingest whose
        renders/crops/canonical-PDF differ byte-wise (a config or engine change) would leak the old
        objects in S3 + the registry forever. So the set of blobs the document referenced BEFORE the
        purge is snapshotted, and after the fresh rows land any of those now-unreferenced (re-checked
        at delete time, so a hash still shared by another document is kept) is removed — mirroring the
        document DELETE path. The original source bytes survive (still referenced by ``source_hash``).

        Args:
            document_id (uuid.UUID): The admitted document.
            payload (IngestionPayload): The run's rows + learned facts.
            warning_reason (str | None): A non-fatal warning to stamp on the DONE document — set by
                the worker when a run completed cleanly but delivered zero chunks (nothing
                retrievable). None (the normal path) clears any stale warning on re-ingest.
        """
        async with self._postgres.session() as session:
            # 0. Snapshot the blobs the document references NOW — the supersede candidates, gathered
            #    BEFORE the purge so the OLD renders/crops/canonical-PDF are captured.
            superseded_candidates = await BlobApi.collect_hashes_for_document(session, document_id)
            # 1. The facts the pipeline learned about the document.
            await DocumentApi.update_facts(
                session,
                document_id,
                title=payload.title,
                language=payload.language,
                page_count=payload.page_count,
                source_kind=payload.source_kind,
                pdf_blob_hash=payload.pdf_blob_hash,
                simhash=payload.simhash,
            )
            # 2. Pages + document-scope metadata (replace semantics).
            await DocumentApi.replace_pages(session, document_id, payload.pages)
            await DocumentApi.replace_metadata(session, document_id, payload.document_metadata)
            # 3. Purge the previous run's chunks and IR (re-ingest idempotency), then insert fresh.
            await ChunkApi.delete_for_document(session, document_id)
            await IRApi.delete_for_document(session, document_id)
            await IRApi.persist_ir(
                session,
                payload.blocks,
                block_tables=payload.block_tables,
                block_figures=payload.block_figures,
                enrichments=payload.enrichments,
            )
            await ChunkApi.persist_chunks(
                session,
                payload.chunks,
                payload.composition,
                metadata=payload.chunk_metadata,
            )
            # 4. The persisted truth is complete — unless a force-cancel raced in (guarded DONE). The
            #    chunk count is denormalized here (0 for the empty case) and the optional warning is
            #    stamped so a 0-chunk run reads as DONE-with-warning, not FAILED.
            await DocumentApi.finalize_done(
                session,
                document_id,
                warning_reason=warning_reason,
                chunk_count=len(payload.chunks),
            )
            # 5. Purge the blobs this run superseded: flush so the FRESH pages/figures/PDF hashes are
            #    visible to the reference re-check, then delete only the old hashes nothing references
            #    anymore (a byte-identical render re-used across runs, or the source, is kept).
            await session.flush()
            orphans = await BlobApi.delete_unreferenced(session, superseded_candidates)
        # 6. S3 last, AFTER the commit — a failed object delete only leaves harmless orphan bytes.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        self.logger.info(
            f"Ingestion saved for document {document_id}: "
            f"{len(payload.blocks)} blocks, {len(payload.chunks)} chunks "
            f"({len(orphans)} superseded blob(s) purged)"
        )

    async def mark_processing(self, document_id: uuid.UUID) -> None:
        """
        Move the document PENDING → PROCESSING as the worker claims its job.

        Guarded to the PENDING → PROCESSING edge (see ``DocumentApi.mark_processing``): the terminal
        DONE/FAILED writes at the end of the run always win, so a failure mid-run never leaves the
        document stuck in PROCESSING.
        """
        async with self._postgres.session() as session:
            await DocumentApi.mark_processing(session, document_id)

    async def mark_failed(self, document_id: uuid.UUID) -> None:
        """Flag the document's ingestion as failed (the job carries the error detail)."""
        async with self._postgres.session() as session:
            await DocumentApi.set_status(session, document_id, DocumentStatus.FAILED)

    async def mark_replay_failed(self, document_id: uuid.UUID, warning_reason: str) -> None:
        """
        Record a failed REPLAY without demoting the document (its previous content is still served).

        A replay persists nothing before its single downstream commit, so a failure leaves the prior
        chunks/points intact: the document keeps its DONE/FAILED status and gets a visible warning.
        Only a document with no trustworthy prior status (PENDING/PROCESSING — admission reset it)
        falls back to FAILED.

        Args:
            document_id (uuid.UUID): The replayed document.
            warning_reason (str): The human-readable failure surfaced on the document.
        """
        async with self._postgres.session() as session:
            await DocumentApi.flag_replay_failure(session, document_id, warning_reason)

    async def index(
        self,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        dense_dim: int,
        points: Sequence[QdrantPoint],
    ) -> None:
        """
        Push a document's chunk vectors into Qdrant (replacing its old points) and flag them indexed.

        The Qdrant collection is ensured (lazily created) from the CURRENT metadata schema; a
        dimension change without reindex surfaces as a loud upsert error, never silently. Point ids
        are deterministic per (document, chunk ordinal) (the translator's UUID v5 remap), so the
        fresh points are upserted FIRST — overwriting the previous run's same-ordinal points in place
        — and only THEN are the document's leftover points (ids this run no longer produced: a
        shorter re-chunk, a now-disabled chunk) deleted. A re-ingest is a REPLACE, never an
        accumulation, and a failed upsert leaves the previous points serving instead of none.

        Args:
            collection_id (uuid.UUID): The target collection.
            document_id (uuid.UUID): The document whose points these are — its stale points are
                purged first so a re-ingest never orphans the previous run's vectors.
            dense_dim (int): Dense vector dimension (from the pipeline's embed config).
            points (Sequence[QdrantPoint]): The points (ids = chunk ids) with vectors + payload.
        """
        # 1. Derive the vector space from the schema (and re-check the slug guard defensively).
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        DatabaseHelpers.validate_vector_slugs(schema)
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        missing_fields = await QdrantCollectionApi.ensure(
            self._qdrant.raw,
            name,
            dense_dim=dense_dim,
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
        )
        # 2. Refuse points carrying a named vector the store never declared (before any purge, so a
        #    failed re-ingest keeps the document's previous points) — Qdrant would 400 on the upsert.
        await self._guard_declared_vectors(collection_id, name, schema, points)
        # 3. Upsert FIRST (deterministic ids overwrite the previous run's points in place), THEN purge
        #    the document's leftover points this run did not produce — otherwise they would survive
        #    as orphans (live document_id + enabled payload → polluting the candidate pool). Never
        #    delete-then-upsert: a failed upsert would leave the document with zero points.
        await QdrantIndexApi.upsert(self._qdrant.raw, name, points)
        await QdrantIndexApi.delete_stale_for_document(
            self._qdrant.raw, name, document_id, [point.point_id for point in points]
        )
        # 4. Flag the chunks as indexed.
        async with self._postgres.session() as session:
            await ChunkApi.mark_indexed(session, [uuid.UUID(point.point_id) for point in points])
        # 5. Advance the indexed baseline: the vectors just landed under the CURRENT config, so stamp
        #    its signature and clear needs_reindex (a real reindex is now the ONLY thing that clears
        #    the flag — the old sticky boolean never did). Best-effort: a failure here must not fail an
        #    ingestion already persisted+upserted (the doc IS indexed; the baseline heals on the next
        #    successful ingest or a config write's derive).
        #    KNOWN LIMITATION: this advances on ANY successful doc ingestion, so a PARTIAL reindex
        #    (only some documents) optimistically clears the flag even if older docs remain on the
        #    previous signature. Acceptable V1 — the documented remediation for a config drift is a
        #    FULL bulk reingest (which DocForge's reindex performs), after which every doc matches.
        #    NEVER advance while the store lacks a semantic/lexical field's named vector: the baseline
        #    would claim the CURRENT schema is indexed although that field is unsearchable (Qdrant
        #    cannot add a vector to a live collection — a reingest never fixes it, an index rebuild does).
        if missing_fields:
            await self._hold_reindex_flag(collection_id, missing_fields)
        else:
            await self._advance_indexed_baseline(collection_id, schema)
        self.logger.info(f"Indexed {len(points)} points into '{name}'")

    async def _guard_declared_vectors(
        self,
        collection_id: uuid.UUID,
        name: str,
        schema: Sequence,
        points: Sequence[QdrantPoint],
    ) -> None:
        """Fail the ingest clearly when a point carries a metadata vector the store does not declare.

        A chunk-scope semantic field made searchable after the collection's first ingest has no named
        vector in the store (Qdrant cannot add one to a live collection), so every upsert would fail
        with Qdrant's opaque "Not existing vector name". The content vectors are always declared by
        ``ensure``; only ``meta_*`` names are checked, and the store is read only when one is carried.

        Args:
            collection_id (uuid.UUID): The target collection (named in the rebuild instruction).
            name (str): Its Qdrant collection name.
            schema (Sequence): Its metadata schema (maps a vector name back to its field).
            points (Sequence[QdrantPoint]): The points about to be upserted.

        Raises:
            UndeclaredVectorError: When a carried metadata vector is not declared by the store.
        """
        # 1. Only metadata vectors can be missing — no store read for a content-only ingest.
        carried = {
            vector
            for point in points
            for vector in (*point.dense, *point.sparse)
            if vector.startswith("meta_")
        }
        if not carried:
            return
        # 2. Compare against the store's declared names; name each offending field.
        declared_dense, declared_sparse = await QdrantCollectionApi.declared_vectors(
            self._qdrant.raw, name
        )
        undeclared = sorted(carried - set(declared_dense) - set(declared_sparse))
        if undeclared:
            field_of = {
                vector: field.field_name
                for field in schema
                for vector in (
                    VectorNames.field_dense(field.field_name),
                    VectorNames.field_sparse(field.field_name),
                )
            }
            raise UndeclaredVectorError.for_vectors(collection_id, undeclared, field_of)

    async def _hold_reindex_flag(self, collection_id: uuid.UUID, missing_fields: set[str]) -> None:
        """Keep ``needs_reindex`` raised (baseline untouched) while the store lacks named vectors.

        Best-effort like the baseline advance: a failure here never fails an already-indexed ingest.

        Args:
            collection_id (uuid.UUID): The just-indexed collection.
            missing_fields (set[str]): The semantic/lexical fields whose named vector is undeclared.
        """
        try:
            # 1. Leave indexed_signature as-is and (re)assert the flag — the store is not aligned.
            async with self._postgres.session() as session:
                await CollectionApi.update(session, collection_id, needs_reindex=True)
            self.logger.warning(
                f"Collection {collection_id}: indexed baseline NOT advanced — fields "
                f"{sorted(missing_fields)} have no named vector in the store (index rebuild required)"
            )
        except Exception as exc:  # best-effort: a trailing flag write must never fail an ingest.
            self.logger.warning(f"Could not hold needs_reindex for {collection_id}: {exc}")

    async def _advance_indexed_baseline(self, collection_id: uuid.UUID, schema: Sequence) -> None:
        """Stamp the collection's indexed_signature to the current config and clear needs_reindex.

        Idempotent and best-effort: re-running the same ingest recomputes the same signature, and any
        failure is swallowed so an already-persisted ingestion never fails at this trailing step.

        Args:
            collection_id (uuid.UUID): The just-indexed collection.
            schema (Sequence): The metadata schema the vectors were indexed under (reused from index).
        """
        try:
            # 1. Read the current pipeline blob, compute the signature over (blob + schema), stamp it.
            async with self._postgres.session() as session:
                collection = await CollectionApi.get(session, collection_id)
                if collection is None:
                    return
                signature = CollectionIndexSignature.compute(collection.pipeline, schema)
                await CollectionApi.update(
                    session,
                    collection_id,
                    indexed_signature=signature,
                    indexed_embed_signature=CollectionIndexSignature.embed_signature(
                        collection.pipeline
                    ),
                    needs_reindex=False,
                )
        except (
            Exception
        ) as exc:  # best-effort: a trailing baseline advance must never fail an ingest.
            self.logger.warning(f"Could not advance indexed baseline for {collection_id}: {exc}")


__all__ = ["IngestionFacade"]
